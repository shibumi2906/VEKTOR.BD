"""HTTP acceptance against running real models; no API calls to paid providers."""

import asyncio
import json
import time
from pathlib import Path
from uuid import UUID

import httpx
import numpy as np

from app.config.settings import Settings
from app.services.database import connect


async def main():
    settings = Settings()
    headers = {"Authorization": "Bearer " + settings.admin_api_token.get_secret_value()}
    topics = json.loads(Path("benchmarks/topics.json").read_text("utf-8"))
    connection = await connect(settings)
    report = {"holdout": [], "negative": [], "latencies": {}}
    try:
        async with httpx.AsyncClient(
            base_url="http://api:8000", headers=headers, timeout=100
        ) as client:
            response = await client.get("/documents?limit=500")
            response.raise_for_status()
            documents = {
                d["document_alias"]: d["document_id"] for d in response.json()["documents"]
            }
            for alias, clause, questions in topics["holdout"]:
                for question in questions:
                    response = await client.post(
                        "/query",
                        json={
                            "question": question,
                            "response_mode": "search",
                            "document_ids": [documents[alias]],
                            "mode": "project_documents",
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    valid = True
                    for source in result["sources"]:
                        row = await connection.fetchrow(
                            """SELECT b.original_text,b.locator FROM registry.blocks b
                            JOIN registry.chunks c ON c.parsing_revision=b.parsing_revision
                            WHERE c.chunk_id=$1 AND b.block_id=$2""",
                            UUID(source["chunk_id"]),
                            UUID(source["block_id"]),
                        )
                        valid &= (
                            row is not None
                            and source["quote"]
                            == row["original_text"][source["span_start"] : source["span_end"]]
                        )
                        valid &= source["document_id"] == documents[alias]
                    assert valid, "Citation/source span mismatch"
                    report["holdout"].append(
                        {
                            "alias": alias,
                            "clause": clause,
                            "question": question,
                            "status": result["status"],
                            "expected_clause_found": any(
                                s["clause"] == clause for s in result["sources"]
                            ),
                            "exact_citations": valid,
                        }
                    )
                print(json.dumps({"tested_topic": alias + ":" + clause}), flush=True)
            for question in topics["negative_holdout"]:
                response = await client.post(
                    "/query", json={"question": question, "response_mode": "search"}
                )
                response.raise_for_status()
                report["negative"].append(
                    {
                        "status": response.json()["status"],
                        "sources": len(response.json()["sources"]),
                    }
                )

            async def measured():
                started = time.monotonic()
                response = await client.post(
                    "/query", json={"question": "מה מטרת תקן 21.1?", "response_mode": "search"}
                )
                response.raise_for_status()
                assert response.json()["status"] == "search_results"
                return time.monotonic() - started

            for concurrency in (1, 2):
                times = []
                for _ in range(5):
                    times.extend(await asyncio.gather(*(measured() for _ in range(concurrency))))
                report["latencies"][str(concurrency)] = {
                    "requests": len(times),
                    "p50_seconds": float(np.percentile(times, 50)),
                    "p95_seconds": float(np.percentile(times, 95)),
                }
            report["summary"] = {
                "holdout_cases": len(report["holdout"]),
                "clause_recall_after_threshold": sum(
                    r["expected_clause_found"] for r in report["holdout"]
                )
                / len(report["holdout"]),
                "exact_citations": "passed",
                "negative_false_accepts": sum(r["sources"] > 0 for r in report["negative"]),
                "live_provider": "not_run: OPENAI_API_KEY absent",
                "legal_corpus": "16 chains unconfirmed",
            }
            Path("data/acceptance-local.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(report["summary"]), flush=True)
            print(json.dumps(report["latencies"]), flush=True)
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
