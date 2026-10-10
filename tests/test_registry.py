import hashlib
import os
from pathlib import Path

import asyncpg
import pytest

from app.config.settings import Settings
from app.registry.corpus import prepare_documents


@pytest.mark.skipif(os.environ.get("REGISTRY_INTEGRATION") != "1", reason="Requires PostgreSQL")
async def test_schema_on_empty_namespace():
    connection = await asyncpg.connect(
        Settings()
        .postgres_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://", 1)
    )
    transaction = connection.transaction()
    await transaction.start()
    try:
        sql = (Path(__file__).parents[1] / "migrations/registry.sql").read_text("utf-8")
        sql = sql.replace("registry.", "registry_test_empty.").replace(
            "CREATE SCHEMA registry;", "CREATE SCHEMA registry_test_empty;"
        )
        await connection.execute(sql)
        assert (
            await connection.fetchval("SELECT count(*) FROM registry_test_empty.document_register")
            == 0
        )
    finally:
        await transaction.rollback()
        await connection.close()


def fixture_manifest(workspace: Path):
    file = workspace / "data/raw/original.pdf"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"%PDF-test immutable original")
    return {
        "documents": [
            {
                "download_status": "downloaded",
                "file": "data/raw/original.pdf",
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            }
        ]
    }


def test_store_original_and_repeat(tmp_path):
    manifest = fixture_manifest(tmp_path)
    root = tmp_path / "volume"
    first = prepare_documents(manifest, tmp_path, root)
    assert prepare_documents(manifest, tmp_path, root) == first
    assert (root / first[0][1]).read_bytes() == (tmp_path / "data/raw/original.pdf").read_bytes()


def test_reject_modified_original(tmp_path):
    manifest = fixture_manifest(tmp_path)
    (tmp_path / "data/raw/original.pdf").write_bytes(b"modified")
    with pytest.raises(ValueError, match="checksum"):
        prepare_documents(manifest, tmp_path, tmp_path / "volume")


def test_reject_outside_storage(tmp_path):
    manifest = fixture_manifest(tmp_path)
    manifest["documents"][0]["file"] = "../../private.pdf"
    with pytest.raises(ValueError, match="outside"):
        prepare_documents(manifest, tmp_path, tmp_path / "volume")


def test_reject_corrupt_stored_copy(tmp_path):
    manifest = fixture_manifest(tmp_path)
    root = tmp_path / "volume"
    first = prepare_documents(manifest, tmp_path, root)
    (root / first[0][1]).write_bytes(b"corrupt volume")
    with pytest.raises(ValueError, match="Stored original"):
        prepare_documents(manifest, tmp_path, root)


@pytest.mark.skipif(os.environ.get("REGISTRY_INTEGRATION") != "1", reason="Requires corpus DB")
async def test_postgres_registry_constraints():
    connection = await asyncpg.connect(
        Settings()
        .postgres_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://", 1)
    )
    try:
        rows = await connection.fetch(
            "SELECT document_id,family_id FROM registry.document_versions LIMIT 2"
        )
        assert len(rows) == 2
        for sql, values, exception in [
            (
                "UPDATE registry.document_families SET current_document_id=$1 WHERE family_id=$2",
                (rows[0]["document_id"], rows[1]["family_id"]),
                asyncpg.ForeignKeyViolationError,
            ),
            (
                "UPDATE registry.document_versions SET file_sha256=$1 WHERE document_id=$2",
                ("0" * 64, rows[0]["document_id"]),
                asyncpg.RaiseError,
            ),
            (
                "UPDATE registry.document_versions SET legal_status=$1 WHERE document_id=$2",
                ("invented", rows[0]["document_id"]),
                asyncpg.CheckViolationError,
            ),
        ]:
            transaction = connection.transaction()
            await transaction.start()
            try:
                with pytest.raises(exception):
                    await connection.execute(sql, *values)
            finally:
                await transaction.rollback()
        assert (
            await connection.fetchval(
                """SELECT count(*) FROM registry.document_register
            WHERE verification_status='manual_review' AND current_norms_eligible"""
            )
            == 0
        )
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM registry.document_versions "
                "WHERE ingestion_status='ready' AND active_index_generation_id IS NULL"
            )
            == 0
        )
    finally:
        await connection.close()
