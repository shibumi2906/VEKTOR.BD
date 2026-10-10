import json
from uuid import uuid4

from app.registry.legal_engine import canonical_hash
from app.services.errors import DomainError


async def enqueue(connection, actor, route, key, kind, payload, document_id=None):
    if not key or len(key) > 200:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", 422)
    digest = canonical_hash(payload)
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock(210027)")
        old = await connection.fetchrow(
            "SELECT * FROM registry.idempotency_records WHERE actor_id=$1 AND route=$2 AND key=$3",
            actor["actor_id"],
            route,
            key,
        )
        if old:
            if old["request_hash"] != digest:
                raise DomainError("IDEMPOTENCY_CONFLICT")
            return json.loads(old["response"])
        identifier = uuid4()
        response = {
            "job_id": str(identifier),
            "document_id": str(document_id) if document_id else None,
        }
        await connection.execute(
            """INSERT INTO registry.jobs(job_id,actor_id,document_id,type,status,payload)
            VALUES($1,$2,$3,$4,'pending',$5)""",
            identifier,
            actor["actor_id"],
            document_id,
            kind,
            json.dumps(payload),
        )
        await connection.execute(
            "INSERT INTO registry.idempotency_records VALUES($1,$2,$3,$4,$5)",
            actor["actor_id"],
            route,
            key,
            digest,
            json.dumps(response),
        )
        return response


async def claim(connection, lease_seconds):
    return await connection.fetchrow(
        """UPDATE registry.jobs SET status='running',attempt=attempt+1,heartbeat_at=now(),
        lease_until=now()+$1*interval '1 second',stage='started'
        WHERE job_id=(SELECT job_id FROM registry.jobs WHERE NOT cancel_requested AND attempt<3
        AND (status='pending' OR (status='running' AND lease_until<now()))
        AND (retry_at IS NULL OR retry_at<=now()) ORDER BY created_at
        FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""",
        lease_seconds,
    )
