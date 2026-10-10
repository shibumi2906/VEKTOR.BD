import os
from uuid import uuid4

import pytest

from app.jobs.queue import claim, enqueue
from app.registry.corpus import identity
from app.services.errors import DomainError
from tests.test_chunk_registry import database as database_fixture

database = database_fixture

pytestmark = pytest.mark.skipif(
    os.environ.get("REGISTRY_INTEGRATION") != "1", reason="Migrated PG required"
)


async def test_job_idempotency_conflicts_and_lease_reclaim(database):
    actor = {"actor_id": uuid4(), "role": "admin"}
    await database.execute(
        "INSERT INTO registry.actors VALUES($1,'admin',$2,true)", actor["actor_id"], str(uuid4())
    )
    payload = {"source_id": "gov"}
    first = await enqueue(database, actor, "/fixture", "key", "source_check", payload)
    assert await enqueue(database, actor, "/fixture", "key", "source_check", payload) == first
    with pytest.raises(DomainError, match="IDEMPOTENCY_CONFLICT"):
        await enqueue(
            database, actor, "/fixture", "key", "source_check", {"source_id": "different"}
        )
    # Restrict claim to the transaction fixture; real queue must not be mutated by test.
    await database.execute(
        "UPDATE registry.jobs SET retry_at=now()+interval '1 day' WHERE actor_id<>$1",
        actor["actor_id"],
    )
    leased = await claim(database, 120)
    assert str(leased["job_id"]) == first["job_id"]
    assert leased["attempt"] == 1
    assert await claim(database, 120) is None
    await database.execute(
        "UPDATE registry.jobs SET lease_until=now()-interval '1 second' WHERE job_id=$1",
        leased["job_id"],
    )
    retry = await claim(database, 120)
    assert retry["job_id"] == leased["job_id"] and retry["attempt"] == 2


async def test_grant_revocation_hides_private_documents(database):
    from app.services.access import documents

    actor = {"actor_id": identity("synthetic:reader"), "role": "reader"}
    await database.execute(
        "INSERT INTO registry.actors VALUES($1,'reader',$2,true)", actor["actor_id"], str(uuid4())
    )
    project = await database.fetchval(
        "SELECT project_id FROM registry.projects WHERE slug='local-contracts'"
    )
    before = {r["document_id"] for r in await documents(database, actor)}
    await database.execute(
        "INSERT INTO registry.project_grants VALUES($1,$2)", actor["actor_id"], project
    )
    after = {r["document_id"] for r in await documents(database, actor)}
    assert len(after - before) == 2
    await database.execute(
        "DELETE FROM registry.project_grants WHERE actor_id=$1", actor["actor_id"]
    )
    assert {r["document_id"] for r in await documents(database, actor)} == before
