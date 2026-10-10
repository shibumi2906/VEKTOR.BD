"""Local administrator CLI for reviewed legal chains. Does not call an LLM."""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

import asyncpg

from app.config.settings import Settings
from app.models.legal import LawChain
from app.registry.legal_repository import register_law, resolve_law, save_chain


async def run(args):
    connection = await asyncpg.connect(
        Settings()
        .postgres_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://", 1)
    )
    try:
        if args.command == "seed":
            config = json.loads(
                (args.workspace / "config/corpus-downloads.json").read_text("utf-8")
            )
            manifest = json.loads((args.workspace / "data/corpus-manifest.json").read_text("utf-8"))
            async with connection.transaction():
                for family in config["families"]:
                    if family["family_alias"] in manifest["baseline_law_families"]:
                        await register_law(connection, family["family_alias"], family["title_he"])
        elif args.command == "import":
            if not args.input:
                raise ValueError("Reviewed chain JSON input required")
            chain = LawChain.model_validate_json(args.input.read_text("utf-8"))
            print(json.dumps({"chain_id": str(await save_chain(connection, chain))}))
            return
        elif args.command == "resolve":
            if not args.law:
                raise ValueError("Law slug required")
            facts = json.loads(args.facts.read_text("utf-8")) if args.facts else {}
            result = await resolve_law(connection, args.law, args.as_of, facts)
            print(result.model_dump_json())
            return
        rows = await connection.fetch(
            """SELECT l.slug,l.title_he,c.verification_status,c.checked_through,c.next_check_at
            FROM registry.legal_laws l LEFT JOIN registry.legal_chains c
            ON c.chain_id=l.current_chain_id ORDER BY l.slug"""
        )
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, default=str))
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seed", "import", "resolve", "status"])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--input", type=Path)
    parser.add_argument("--law")
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--facts", type=Path)
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception:
        print("Legal registry failed; check reviewed input, migrations and configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main()
