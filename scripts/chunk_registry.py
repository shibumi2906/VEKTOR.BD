"""Import checked chunk artifacts into PostgreSQL without activating retrieval."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import asyncpg

from app.chunking.repository import stage_artifact
from app.config.settings import Settings


async def run(workspace):
    root = workspace / "data/chunks"
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    connection = await asyncpg.connect(
        Settings()
        .postgres_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://", 1)
    )
    try:
        totals = {"documents": 0, "blocks": 0, "chunks": 0}
        async with connection.transaction():
            for row in manifest["documents"]:
                path = (root / row["artifact"]).resolve()
                if not path.is_relative_to(root.resolve()):
                    raise ValueError("Artifact outside staging")
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                if sha != row["sha256"]:
                    raise ValueError("Artifact hash mismatch")
                artifact = json.loads(path.read_text("utf-8"))
                counts = await stage_artifact(connection, artifact, row["artifact"], sha)
                totals["documents"] += 1
                totals["blocks"] += counts["blocks"]
                totals["chunks"] += counts["chunks"]
        print(json.dumps({**totals, "search_activated": False}))
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    asyncio.run(run(parser.parse_args().workspace.resolve()))
