import json
import os
from pathlib import Path

import asyncpg
import pytest

from app.config.settings import Settings
from app.models.legal import LawChain
from app.registry.legal_repository import register_law, resolve_law, save_chain
from app.retrieval.legal_scope import (
    LegalScopeBlocked,
    prepare_legal_scope,
    retrieve_current_legal_evidence,
    revalidate_legal_scope,
)
from tests.fixtures.legal_cases import NEW, NOW, chain_data

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
    transaction = connection.transaction(isolation="repeatable_read")
    await transaction.start()
    try:
        await connection.execute(
            """INSERT INTO registry.source_registry VALUES
            ('synthetic_authority','official','Synthetic test authority',3600,$1,now())""",
            json.dumps({"allowed_hosts": ["example.invalid"], "allowed_path_prefixes": ["/"]}),
        )
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


async def test_fresh_schema_with_both_migrations(database):
    root = Path(__file__).parents[1] / "migrations"
    sql = (root / "registry.sql").read_text("utf-8") + (root / "legal_chains.sql").read_text(
        "utf-8"
    )
    sql = sql.replace("registry.", "registry_test_legal.").replace(
        "CREATE SCHEMA registry;", "CREATE SCHEMA registry_test_legal;"
    )
    await database.execute(sql)
    assert await database.fetchval("SELECT count(*) FROM registry_test_legal.legal_snapshots") == 0


async def test_raw_pdf_verified_flags_cannot_bypass_legal_engine(database):
    transaction = database.transaction()
    await transaction.start()
    try:
        document = await database.fetchval(
            "SELECT document_id FROM registry.document_versions WHERE category='standard' LIMIT 1"
        )
        await database.execute(
            "UPDATE registry.document_versions SET category='consolidated_law' "
            "WHERE document_id=$1",
            document,
        )
        row = await database.fetchrow(
            "SELECT current_norms_eligible,legal_engine_required FROM registry.document_register "
            "WHERE document_id=$1",
            document,
        )
        assert row["legal_engine_required"] and not row["current_norms_eligible"]
    finally:
        await transaction.rollback()


async def test_real_repository_repeat_import_and_immutable_snapshot(database):
    chain = LawChain.model_validate(chain_data())
    chain_id = await save_chain(database, chain)
    assert await save_chain(database, chain) == chain_id
    assert (
        await database.fetchval(
            "SELECT count(*) FROM registry.legal_chains WHERE chain_id=$1", chain_id
        )
        == 1
    )
    result = await resolve_law(database, chain.law_slug, facts={}, now=NOW)
    assert result.status == "verified" and result.clauses[0].text_he == NEW
    assert (
        await resolve_law(database, chain.law_slug, now=NOW)
    ).snapshot_sha256 == result.snapshot_sha256
    assert (
        await database.fetchval(
            "SELECT count(*) FROM registry.legal_snapshots WHERE chain_id=$1", chain_id
        )
        == 1
    )
    transaction = database.transaction()
    await transaction.start()
    try:
        with pytest.raises(asyncpg.RaiseError):
            await database.execute(
                "UPDATE registry.legal_snapshots SET payload='{}' WHERE snapshot_sha256=$1",
                result.snapshot_sha256,
            )
    finally:
        await transaction.rollback()


async def test_incomplete_or_unregistered_input_cannot_provide_evidence(database):
    data = chain_data()
    data["review"]["complete"] = False
    chain_id = await save_chain(database, LawChain.model_validate(data))
    result = await resolve_law(database, "synthetic_rule", now=NOW)
    assert result.status == "chain_incomplete" and not result.clauses
    assert (
        await database.fetchval(
            "SELECT count(*) FROM registry.legal_snapshots WHERE chain_id=$1", chain_id
        )
        == 0
    )
    data = chain_data()
    data["clauses"][0]["source"]["url"] = "https://unregistered.invalid/file.pdf"
    with pytest.raises(ValueError, match="registered"):
        await save_chain(database, LawChain.model_validate(data))


async def test_multi_law_scope_is_all_or_nothing_and_rechecks_changes(database):
    await save_chain(database, LawChain.model_validate(chain_data()))
    with pytest.raises(LegalScopeBlocked) as blocked:
        await prepare_legal_scope(database, ["synthetic_rule", "missing_law"], now=NOW)
    assert blocked.value.statuses == {"missing_law": "chain_incomplete"}
    scope = await prepare_legal_scope(database, ["synthetic_rule"], now=NOW)
    await revalidate_legal_scope(database, scope, now=NOW)
    updated = chain_data()
    updated["amendments"][0]["changes"][0]["new_text_he"] = "התקופה היא תשעים ימים."
    await save_chain(database, LawChain.model_validate(updated))
    with pytest.raises(LegalScopeBlocked) as changed:
        await revalidate_legal_scope(database, scope, now=NOW)
    assert changed.value.code == "SOURCE_CHANGED"


async def test_current_chain_cannot_belong_to_another_law(database):
    chain_id = await save_chain(database, LawChain.model_validate(chain_data()))
    other = await register_law(database, "synthetic_other", "כלל סינתטי נוסף")
    transaction = database.transaction()
    await transaction.start()
    try:
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await database.execute(
                "UPDATE registry.legal_laws SET current_chain_id=$1 WHERE law_id=$2",
                chain_id,
                other,
            )
    finally:
        await transaction.rollback()


async def test_retrieval_adapter_never_runs_for_missing_law(database):
    called = False

    async def search(scope):
        nonlocal called
        called = True
        return []

    with pytest.raises(LegalScopeBlocked):
        await retrieve_current_legal_evidence(database, ["missing_law"], search, now=NOW)
    assert not called


async def test_retrieval_wrapper_returns_only_matching_current_spans(database):
    await save_chain(database, LawChain.model_validate(chain_data()))

    async def search(scope):
        snapshot = scope.snapshots[0]
        return [
            {
                "law_slug": snapshot.law_slug,
                "clause_id": "1",
                "snapshot_sha256": snapshot.snapshot_sha256,
                "start": 0,
                "end": len(NEW),
                "text_he": NEW,
            }
        ]

    scope, evidence = await retrieve_current_legal_evidence(
        database, ["synthetic_rule"], search, now=NOW
    )
    assert evidence[0]["text_he"] == NEW and len(evidence[0]["provenance"]) == 2
    assert evidence[0]["snapshot_sha256"] == scope.snapshots[0].snapshot_sha256

    async def outdated_search(scope):
        hits = await search(scope)
        hits[0]["snapshot_sha256"] = "0" * 64
        return hits

    with pytest.raises(ValueError, match="MISMATCH"):
        await retrieve_current_legal_evidence(
            database, ["synthetic_rule"], outdated_search, now=NOW
        )
