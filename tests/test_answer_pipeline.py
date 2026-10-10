import json
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest

from app.citations.builder import citation
from app.config.settings import Settings
from app.llm.provider import Provider, object_schema, validate_schema
from app.models.query import CompareRequest, QueryRequest
from app.services.comparison import compare
from app.services.errors import DomainError
from app.services.query import answer


class Connection:
    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, *args):
        pass

    async def fetchval(self, *args):
        return 0.0

    async def fetchrow(self, sql, *args):
        if "registry.blocks" in sql:
            return {"original_text": "חניה אחת", "locator": {"displayed_page": 1}}
        return {
            "title": "Synthetic",
            "category": "contract",
            "document_role": "contract",
            "legal_status": "not_applicable",
            "verification_status": "manual_review",
            "issuer": "Fixture",
        }


@pytest.mark.parametrize(
    "question, accepted", [("Парковка", True), ("Что делает адвокат жильцов?", False)]
)
async def test_claim_semantic_verdict_and_exact_quotes(question, accepted):
    chunk, block, doc, revision = [str(uuid4()) for _ in range(4)]
    candidate = {
        "chunk_id": chunk,
        "document_id": doc,
        "parsing_revision": revision,
        "category": "contract",
        "text": "חניה אחת",
        "content_sha256": "a" * 64,
        "section": "1",
        "clause": "1.1",
        "spans": [{"block_id": block, "start": 0, "end": 8, "locator": {"displayed_page": 1}}],
    }

    class Model:
        async def structured(self, instructions, data, schema, name):
            assert isinstance(instructions, str)
            if name == "claims":
                return {
                    "claims": [
                        {
                            "claim_id": "supported",
                            "text": "Одна парковка",
                            "evidence_ids": [
                                data["evidence"][0]["evidence_spans"][0]["evidence_id"]
                            ],
                        }
                    ]
                }
            assert data["sources"][0]["quote"] == "חניה אחת"
            assert data["question"] == question
            assert "relevance to the ORIGINAL question" in instructions
            return {"accepted_ids": ["supported"] if accepted else []}

    claims, sources = await answer(
        Connection(), Model(), QueryRequest(question=question), [candidate], "ru"
    )
    if accepted:
        assert claims[0]["citation_ids"] == [sources[0]["citation_id"]]
        assert sources[0]["quote"] == "חניה אחת"
    else:
        assert claims == sources == []
    forged = {**candidate, "spans": [{"block_id": block, "start": 0, "end": 2, "locator": {}}]}
    with pytest.raises(DomainError, match="CITATION_SCOPE_MISMATCH"):
        await citation(
            Connection(),
            forged,
            {"chunk_id": chunk, "block_id": block, "span_start": 0, "span_end": 8},
        )


async def test_unknown_evidence_drops_whole_claim_without_using_partial_citations():
    chunk, block, doc, revision = [str(uuid4()) for _ in range(4)]
    candidate = {
        "chunk_id": chunk,
        "document_id": doc,
        "parsing_revision": revision,
        "category": "contract",
        "text": "חניה אחת",
        "content_sha256": "a" * 64,
        "section": "1",
        "clause": "1.1",
        "spans": [{"block_id": block, "start": 0, "end": 8, "locator": {}}],
    }

    class Model:
        async def structured(self, instructions, data, schema, name):
            assert name == "claims"  # No semantic validation for discarded claims.
            assert schema["properties"]["claims"]["items"]["properties"]["evidence_ids"]["items"][
                "enum"
            ] == ["E1"]
            return {
                "claims": [
                    {"claim_id": "bad", "text": "Одна парковка", "evidence_ids": ["E1", "E999"]}
                ]
            }

    assert await answer(
        Connection(), Model(), QueryRequest(question="חניה"), [candidate], "he"
    ) == ([], [])


def test_provider_rejects_out_of_scope_evidence_id():
    from app.llm.provider import claims_schema

    with pytest.raises(ValueError, match="outside allowed evidence"):
        validate_schema(
            {"claims": [{"claim_id": "bad", "text": "bad", "evidence_ids": ["E999"]}]},
            claims_schema(["E1"]),
        )


async def test_comparison_runs_independent_scopes_and_validates_difference(monkeypatch):
    from app.services import comparison

    ids = [uuid4(), uuid4()]
    searches = []

    class Retrieval:
        async def scope(self, connection, actor, request):
            return [{"generation": uuid4(), "document_id": request.document_ids[0]}]

        async def search(self, connection, actor, scope, query):
            searches.append(scope[0]["document_id"])
            return [{"doc": scope[0]["document_id"]}]

        async def revalidate(self, *args):
            pass

    class Model:
        usage = []

        def __init__(self, *args):
            pass

        async def structured(self, instructions, data, schema, name):
            assert isinstance(instructions, str)
            return (
                {"difference": "Одно и два места"}
                if name == "topic_difference"
                else {"supported": True}
            )

    async def supported(connection, provider, request, chunks, language):
        return [{"text": "Одна парковка" if chunks[0]["doc"] == ids[0] else "Две парковки"}], [
            {"document_id": str(chunks[0]["doc"])}
        ]

    monkeypatch.setattr(comparison, "Provider", Model)
    monkeypatch.setattr(comparison, "answer", supported)
    settings = Settings(_env_file=None, app_mode="bootstrap", openai_api_key="offline-placeholder")
    request = CompareRequest(question="חניה", document_a=ids[0], document_b=ids[1])
    report = await compare(
        Connection(),
        {"role": "admin", "actor_id": uuid4()},
        Retrieval(),
        settings,
        request,
        uuid4(),
    )
    assert searches == ids
    assert report["status"] == "compared"
    assert report["findings"][0]["citations_a"][0]["document_id"] == str(ids[0])
    assert report["findings"][0]["citations_b"][0]["document_id"] == str(ids[1])


async def test_provider_strict_output_retry_and_store_false(monkeypatch):
    original = httpx.AsyncClient
    calls = []

    async def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "usage": {"input_tokens": 20, "output_tokens": 10},
                "output": [{"content": [{"type": "output_text", "text": '{"result":"ok"}'}]}],
            },
        )

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler))
    )
    settings = Settings(
        _env_file=None,
        app_mode="bootstrap",
        openai_api_key="offline-placeholder",
        max_output_tokens=100,
        query_cost_limit=0.1,
        max_context_tokens=10000,
    )
    provider = Provider(settings, Connection(), uuid4())
    assert await provider.structured(
        "Prompt", {}, object_schema({"result": {"type": "string"}}), "fixture"
    ) == {"result": "ok"}
    assert calls[0]["model"] == "gpt-5.4-mini"
    assert calls[1]["model"] == "gpt-4.1-mini"
    assert provider.spent > provider.usage[0]["estimated_cost"]


@pytest.mark.parametrize("value", [{"ok": True, "extra": 1}, {"ok": "yes"}, {}, []])
def test_provider_invalid_output(value):
    with pytest.raises(ValueError):
        validate_schema(value, object_schema({"ok": {"type": "boolean"}}))
