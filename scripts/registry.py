"""Local administrator CLI; inherits database credentials without displaying them."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

from app.config.settings import Settings
from app.registry.corpus import import_corpus, prepare_documents


async def run(args):
    settings = Settings()
    connection = await asyncpg.connect(
        settings.postgres_url.get_secret_value().replace(
            "postgresql+asyncpg://", "postgresql://", 1
        ),
        timeout=10,
    )
    try:
        if args.command == "import":
            manifest = json.loads((args.workspace / "data/corpus-manifest.json").read_text("utf-8"))
            sources = json.loads((args.workspace / "config/sources.yaml").read_text("utf-8"))
            prepared = prepare_documents(manifest, args.workspace, settings.raw_storage_path)
            await import_corpus(connection, manifest, sources, prepared)
        if args.command == "list":
            rows = await connection.fetch(
                "SELECT * FROM registry.document_register ORDER BY document_alias"
            )
            print(json.dumps([dict(row) for row in rows], ensure_ascii=False, default=str))
        else:
            counts = {}
            for table in (
                "document_versions",
                "source_registry",
                "source_checks",
                "coverage_gaps",
                "audit_events",
            ):
                counts[table] = await connection.fetchval(f"SELECT count(*) FROM registry.{table}")
            counts["pages"] = await connection.fetchval(
                "SELECT COALESCE(sum(page_count),0) FROM registry.document_versions"
            )
            counts["failed_downloads"] = await connection.fetchval(
                "SELECT count(*) FROM registry.source_checks WHERE download_status='failed'"
            )
            print(json.dumps(counts))
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["import", "summary", "list"])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception:
        # Database exceptions can embed credentials or private paths.
        print("Registry operation failed; check configuration, migrations and corpus integrity.")
        sys.exit(1)


if __name__ == "__main__":
    main()
