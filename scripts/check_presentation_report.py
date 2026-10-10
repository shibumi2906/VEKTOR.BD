"""Inspect latest PUBLIC result and cost metadata without printing source text."""

import asyncio
import json
from pathlib import Path

from app.config.settings import Settings
from app.services.database import connect


async def main():
    db = await connect(Settings())
    row = await db.fetchrow(
        "SELECT request_id,payload FROM registry.query_reports ORDER BY created_at DESC LIMIT 1"
    )
    payload = json.loads(row["payload"])
    for source in payload["sources"]:
        project = await db.fetchval(
            "SELECT f.project_id FROM registry.document_versions v "
            "JOIN registry.document_families f USING(family_id) WHERE v.document_id=$1",
            source["document_id"],
        )
        assert project is None, "Only public reports may be exported"
    usages = await db.fetch(
        "SELECT payload FROM registry.provider_usage WHERE request_id=$1", row["request_id"]
    )
    metrics = {
        "status": payload["status"],
        "claims": len(payload.get("claims", [])),
        "sources": len(payload["sources"]),
        "translated": sum(bool(s.get("quote_translation")) for s in payload["sources"]),
        "usage": [json.loads(r["payload"]) for r in usages],
    }
    metrics["daily_reserved"] = await db.fetchval(
        "SELECT sum(reserved_usd) FROM registry.provider_reservations "
        "WHERE (created_at AT TIME ZONE 'Asia/Jerusalem')::date="
        "(now() AT TIME ZONE 'Asia/Jerusalem')::date"
    )
    Path("data/readable-answer-check.json").write_text(
        json.dumps({"metrics": metrics, "response": payload}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(metrics))
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
