"""Reparse all registered immutable originals without changing legal review statuses."""

import asyncio
import json

from app.config.settings import Settings
from app.parsing.registered import parse_registered
from app.services.database import connect


async def main():
    settings = Settings()
    connection = await connect(settings)
    results = []
    try:
        rows = await connection.fetch(
            "SELECT document_id FROM registry.document_versions "
            "WHERE category<>'consolidated_law' ORDER BY document_id"
        )
        for row in rows:
            results.append(await parse_registered(connection, settings, row["document_id"]))
            print(json.dumps({"parsed": len(results), "chunks": results[-1]["chunks"]}), flush=True)
        (settings.index_storage_path / "parsing-final-report.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
