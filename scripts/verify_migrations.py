"""Migrate empty and previous-stage databases; never alter the production database."""

import asyncio
import os
import subprocess
from datetime import UTC, datetime

from pydantic import SecretStr

from app.config.settings import Settings
from app.services.database import connect


async def main():
    settings = Settings()
    connection = await connect(settings)
    name = "pinui_restore_" + datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    url = settings.postgres_url.get_secret_value().rsplit("/", 1)[0] + "/" + name
    try:
        await connection.execute(f'CREATE DATABASE "{name}"')
        environment = {**os.environ, "POSTGRES_URL": url}
        for revision in ("0004_chunks", "head"):
            result = await asyncio.to_thread(
                subprocess.run,
                ["alembic", "upgrade", revision],
                env=environment,
                capture_output=True,
                timeout=120,
                check=False,
            )
            if result.returncode:
                raise RuntimeError("Migration verification failed: " + revision)
        restored = settings.model_copy(update={"postgres_url": SecretStr(url)})
        scratch = await connect(restored)
        try:
            assert (
                await scratch.fetchval("SELECT version_num FROM alembic_version")
                == "0008_query_reports"
            )
            for table in (
                "document_versions",
                "actors",
                "jobs",
                "index_generations",
                "query_reports",
                "legal_chains",
                "legal_snapshots",
            ):
                assert await scratch.fetchval("SELECT to_regclass($1)", "registry." + table)
        finally:
            await scratch.close()
        print("Empty database -> 0004 -> 0008: passed", flush=True)
    finally:
        # Name generated only from a fixed prefix and timestamp; no user path/DB accepted.
        if await connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)", name
        ):
            await connection.execute(f'DROP DATABASE "{name}"')
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
