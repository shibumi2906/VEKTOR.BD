"""Verify real local HTTP contracts without credentials or paid model calls."""

import asyncio
import hashlib
import json
from pathlib import Path

import httpx

from app.models.responses import CompareResponse, QueryResponse


async def main():
    results = {}
    async with httpx.AsyncClient(base_url="http://api:8000", timeout=100) as client:
        response = await client.get("/documents", params={"limit": 500})
        response.raise_for_status()
        documents = response.json()["documents"]
        results["no_login_documents"] = len(documents)
        private = [d for d in documents if d["category"] == "contract" and d["project_id"]]
        assert len(private) == 2
        results["private_contracts_visible"] = "passed"
        first = await client.get("/documents", params={"limit": 1})
        second = await client.get(
            "/documents", params={"limit": 1, "cursor": first.json()["next_cursor"]}
        )
        assert (
            first.json()["documents"][0]["document_id"]
            != second.json()["documents"][0]["document_id"]
        )
        results["pagination"] = "passed"
        resolve = await client.get("/documents/resolve", params={"reference": "04.2025"})
        resolve.raise_for_status()
        assert resolve.json()["status"] == "resolved"
        for document in private:
            original = await client.get("/documents/" + document["document_id"] + "/original")
            original.raise_for_status()
            details = await client.get("/documents/" + document["document_id"])
            details.raise_for_status()
            assert hashlib.sha256(original.content).hexdigest() == details.json()["file_sha256"]
        results["original_downloads"] = "passed"
        search = await client.post(
            "/query", json={"question": "מה מטרת תקן 21.1?", "response_mode": "search"}
        )
        search.raise_for_status()
        query = QueryResponse.model_validate(search.json())
        assert query.status == "search_results" and query.sources and query.answer is None
        assert all(s.quote and s.span_end > s.span_start for s in query.sources)
        results["search_dto"] = "passed"
        compare = {
            "document_a": private[0]["document_id"],
            "document_b": private[1]["document_id"],
            "question": "Сравни договоры",
        }
        response = await client.post("/compare", json=compare)
        response.raise_for_status()
        assert CompareResponse.model_validate(response.json()).status == "clarification_required"
        results["topic_clarification"] = "passed"
        status = await client.get("/status")
        status.raise_for_status()
        assert status.json()["capabilities"]["search_he"]
        if not status.json()["capabilities"]["llm_configured"]:
            for route, body in (
                ("/compare", {**compare, "question": "Сравни условия парковки"}),
                ("/query", {"question": "מה מטרת תקן 21.1?", "response_mode": "answer"}),
            ):
                response = await client.post(route, json=body)
                assert response.status_code == 409
                assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
            results["missing_key"] = "passed"
        response = await client.post("/query", json={"question": ""})
        assert response.status_code == 422
        assert response.json()["request_id"] == response.headers["X-Request-ID"]
        response = await client.get("/documents", headers={"Origin": "https://foreign.example"})
        assert response.status_code == 403
        results["local_origin_and_errors"] = "passed"
    Path("data/http-final-report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
