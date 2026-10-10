"""Durable leased jobs and source-check scheduling; heartbeat is independent of child work."""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime

from app.acquisition.checks import check_source
from app.config.settings import Settings
from app.jobs.queue import claim, enqueue
from app.registry.corpus import identity
from app.services.database import connect


async def child(module, *args, job=None):
    environment = os.environ.copy()
    if job:
        environment.update(JOB_ID=str(job["job_id"]), JOB_ATTEMPT=str(job["attempt"]))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        module,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=environment,
    )
    try:
        output, _ = await process.communicate()
        if process.returncode:
            raise ValueError("PIPELINE_FAILED")
        return [json.loads(line) for line in output.splitlines() if line.startswith(b"{")]
    except asyncio.CancelledError:
        process.terminate()
        await process.wait()
        raise


async def execute(settings, job):
    if job["type"] == "source_check":
        connection = await connect(settings)
        try:
            return await check_source(connection, settings, json.loads(job["payload"])["source_id"])
        finally:
            await connection.close()
    if job["type"] in ("ingest", "reindex", "index"):
        connection = await connect(settings)
        try:
            checkpoint = await connection.fetchval(
                "SELECT payload FROM registry.job_checkpoints WHERE job_id=$1 AND stage='parsed'",
                job["job_id"],
            )
            if not checkpoint:
                result = await child("scripts.process_document", str(job["document_id"]), job=job)
                await connection.execute(
                    "INSERT INTO registry.job_checkpoints VALUES($1,'parsed',$2) "
                    "ON CONFLICT DO NOTHING",
                    job["job_id"],
                    json.dumps(result),
                )
            await connection.execute(
                "UPDATE registry.jobs SET stage='indexing',progress=0.25 "
                "WHERE job_id=$1 AND attempt=$2",
                job["job_id"],
                job["attempt"],
            )
        finally:
            await connection.close()
    counts = await child("scripts.index_corpus", job=job)
    return {"document_id": str(job["document_id"]), "index_verified": True, "counters": counts[-1]}


async def worker(settings, connection):
    job = await claim(connection, settings.job_lease_seconds)
    if not job:
        return
    task = asyncio.create_task(execute(settings, job))
    error, result, status = None, None, "completed"
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=settings.job_heartbeat_seconds)
            row = await connection.fetchrow(
                "SELECT * FROM registry.jobs WHERE job_id=$1", job["job_id"]
            )
            if row["attempt"] != job["attempt"] or row["cancel_requested"]:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                status = "cancelled"
                break
            await connection.execute(
                """UPDATE registry.jobs SET heartbeat_at=now(),
                lease_until=now()+$3*interval '1 second',stage='processing'
                WHERE job_id=$1 AND attempt=$2 AND status='running'""",
                job["job_id"],
                job["attempt"],
                settings.job_lease_seconds,
            )
        if status == "completed":
            result = task.result()
    except Exception:
        status, error = "failed", "PIPELINE_FAILED"
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await connection.execute(
            """UPDATE registry.jobs SET status=$3,stage=$3,
            progress=CASE WHEN $3='completed' THEN 1 ELSE progress END,
            result=$4,error_code=$5,lease_until=NULL WHERE job_id=$1 AND attempt=$2""",
            job["job_id"],
            job["attempt"],
            status,
            json.dumps(result),
            error,
        )


async def scheduler(settings, connection):
    await connection.execute("""UPDATE registry.jobs SET status='cancelled',stage='cancelled'
        WHERE cancel_requested AND status='pending'""")
    await connection.execute(
        "UPDATE registry.jobs SET status='failed',error_code='LE"
        "ASE_RETRIES_EXHAUSTED'\n        WHERE status='running' A"
        "ND lease_until<now() AND attempt>=3"
    )
    actor = {"actor_id": identity("actor:scheduler"), "role": "admin"}
    await connection.execute(
        "INSERT INTO registry.actors VALUES($1,'admin',$2,true) ON CONFLICT DO NOTHING",
        actor["actor_id"],
        "scheduler-internal-no-login",
    )
    rows = await connection.fetch("""SELECT s.source_id,s.check_interval_seconds,
        max(c.checked_at) AS last_check FROM registry.source_registry s
        LEFT JOIN registry.source_checks c USING(source_id)
        WHERE s.source_type='official' GROUP BY s.source_id""")
    now = datetime.now(UTC)
    for row in rows:
        if (
            row["last_check"] is None
            or (now - row["last_check"]).total_seconds() > row["check_interval_seconds"]
        ):
            await enqueue(
                connection,
                actor,
                "scheduler",
                row["source_id"] + ":" + now.date().isoformat(),
                "source_check",
                {"source_id": row["source_id"]},
            )


async def run(role):
    settings = Settings()
    settings.runtime_path.mkdir(parents=True, exist_ok=True)
    target = settings.runtime_path / f"{role}.heartbeat"
    connection = None

    async def pulse():
        while True:
            temporary = target.with_suffix(".tmp")
            temporary.write_text(str(time.time()))
            temporary.replace(target)
            await asyncio.sleep(settings.job_heartbeat_seconds)

    heartbeat = asyncio.create_task(pulse())
    try:
        while True:
            if settings.app_mode == "production":
                try:
                    if connection is None or connection.is_closed():
                        connection = await connect(settings)
                    await (
                        worker(settings, connection)
                        if role == "worker"
                        else scheduler(settings, connection)
                    )
                except Exception:
                    if connection:
                        await connection.close()
                    connection = None
            await asyncio.sleep(2 if role == "worker" else 30)
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        if connection:
            await connection.close()
        target.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["worker", "scheduler"])
    asyncio.run(run(parser.parse_args().role))
