import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from app.citations.builder import search_citations
from app.config.settings import Settings
from app.models.legal import LawChain
from app.registry.legal_engine import canonical_hash
from app.registry.legal_repository import save_chain
from app.retrieval.engine import Retrieval
from app.retrieval.legal_index import search_legal, snapshot_chunks
from app.retrieval.legal_scope import prepare_legal_scope
from tests.fixtures.legal_cases import NEW, chain_data
from tests.test_legal_registry import database as database_fixture

database = database_fixture

pytestmark = pytest.mark.skipif(
    os.environ.get("REGISTRY_INTEGRATION") != "1", reason="Real local models/Qdrant/PG required"
)


async def test_verified_snapshot_real_vectors_and_derived_citations(database):
    settings = Settings()
    engine = Retrieval(settings)
    data = chain_data()
    now = datetime.now(UTC)
    data["review"].update(
        checked_through=(now + timedelta(days=1)).date().isoformat(),
        checked_at=(now - timedelta(hours=1)).isoformat(),
        next_check_at=(now + timedelta(days=1)).isoformat(),
    )
    await save_chain(database, LawChain.model_validate(data))
    scope = await prepare_legal_scope(database, ["synthetic_rule"])
    fingerprint = canonical_hash(
        {
            "model": engine.manifest["model"],
            "snapshots": [s.snapshot_sha256 for s in scope.snapshots],
        }
    )
    collection = "pinui_legal_" + fingerprint[:24]
    try:
        chunks = snapshot_chunks(scope, engine.manifest["model"])
        assert chunks[0]["text"] == NEW
        hits = await search_legal(database, engine, scope, "מהי התקופה בימים?")
        assert hits
        citations = await search_citations(database, hits)
        assert citations[0]["quote"] == NEW
        assert citations[0]["is_derived_text"] is True
        assert len(citations[0]["provenance"]) == 2
        assert citations[0]["locator"]["displayed_page"] is None
        assert "example.invalid" in json.dumps(citations[0]["provenance"])
        assert await search_legal(database, engine, scope, "מהי התקופה בימים?")
    finally:
        if engine.client.collection_exists(collection):
            engine.client.delete_collection(collection)
        engine.client.close()
