import copy
import json
import os
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from app.chunking.core import create_chunks, parse_pages, verify_artifact
from app.chunking.repository import stage_artifact
from app.config.settings import Settings
from tests.test_chunking import CONFIG, HEBREW

pytestmark = pytest.mark.skipif(
    os.environ.get("REGISTRY_INTEGRATION") != "1", reason="Requires migrated PostgreSQL"
)


@pytest.fixture
async def database():
    connection = await asyncpg.connect(
        Settings()
        .postgres_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://", 1)
    )
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


async def sample(database, config=None):
    row = await database.fetchrow(
        "SELECT * FROM registry.document_versions WHERE category='standard'"
    )
    document = {
        k: row[k]
        for k in (
            "version_status",
            "legal_status",
            "verification_status",
            "document_role",
            "source_id",
            "source_url",
            "category",
            "file_sha256",
        )
    }
    document["document_id"] = str(row["document_id"])
    pages = ["2.1 " + HEBREW * 5]
    revision, blocks, quality = parse_pages(document["document_id"], pages, "d" * 64)
    fingerprint, chunks = create_chunks(document, revision, blocks, config or CONFIG)
    artifact = {
        "document": document,
        "pages": pages,
        "parsing_revision": revision,
        "parser_fingerprint": "d" * 64,
        "blocks": blocks,
        "page_quality": quality,
        "warnings": ["Synthetic rollback-only fixture"],
        "chunks": chunks,
        "chunking_fingerprint": fingerprint,
        "max_tokens": (config or CONFIG)["max_tokens"],
    }
    return artifact


async def test_fresh_schema_chunk_migration(database):
    root = Path(__file__).parents[1] / "migrations"
    sql = "\n".join(
        (root / name).read_text("utf-8")
        for name in ("registry.sql", "legal_chains.sql", "chunks.sql")
    )
    sql = sql.replace("registry.", "registry_test_chunks.").replace(
        "CREATE SCHEMA registry;", "CREATE SCHEMA registry_test_chunks;"
    )
    await database.execute(sql)
    assert await database.fetchval("SELECT count(*) FROM registry_test_chunks.chunks") == 0


async def test_staging_idempotent_with_exact_persisted_citation_and_no_activation(database):
    artifact = await sample(database)
    a = await stage_artifact(database, artifact, "synthetic.json", "e" * 64)
    b = await stage_artifact(database, artifact, "synthetic.json", "e" * 64)
    assert a == b == {"blocks": 1, "chunks": 1}
    chunk = await database.fetchrow(
        "SELECT * FROM registry.chunks WHERE chunk_id=$1", UUID(artifact["chunks"][0]["chunk_id"])
    )
    assert chunk["text"] == artifact["chunks"][0]["text"]
    assert json.loads(chunk["spans"]) == artifact["chunks"][0]["spans"]
    metadata = json.loads(chunk["metadata"])
    assert metadata["index_generation_id"] is None and metadata["current_norms_eligible"] is False
    savepoint = database.transaction()
    await savepoint.start()
    try:
        with pytest.raises(asyncpg.RaiseError):
            await database.execute(
                "UPDATE registry.chunks SET text='changed' WHERE chunk_id=$1", chunk["chunk_id"]
            )
    finally:
        await savepoint.rollback()


async def test_changed_chunk_settings_keep_original_parse_and_new_ids(database):
    original = await sample(database)
    changed = await sample(database, {**CONFIG, "max_tokens": 20, "overlap_tokens": 5})
    await stage_artifact(database, original, "original.json", "e" * 64)
    await stage_artifact(database, changed, "changed.json", "f" * 64)
    assert original["parsing_revision"] == changed["parsing_revision"]
    assert original["chunks"][0]["chunk_id"] != changed["chunks"][0]["chunk_id"]


async def test_registry_status_change_rejects_stale_artifact(database):
    artifact = await sample(database)
    artifact["document"]["verification_status"] = "manual_review"
    for chunk in artifact["chunks"]:
        chunk["verification_status"] = "manual_review"
    with pytest.raises(ValueError, match="metadata changed"):
        await stage_artifact(database, artifact, "synthetic.json", "e" * 64)


async def test_chunk_and_page_binding_reject_corruption(database):
    artifact = await sample(database)
    damaged = copy.deepcopy(artifact)
    damaged["pages"][0] = "replaced source"
    with pytest.raises(ValueError):
        verify_artifact(damaged)
    damaged = copy.deepcopy(artifact)
    damaged["chunks"][0]["document_id"] = "wrong document"
    with pytest.raises(ValueError, match="document metadata"):
        verify_artifact(damaged)
