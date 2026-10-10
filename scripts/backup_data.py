"""Snapshot originals, configuration and Qdrant into an ignored protected local backup."""

import argparse
import asyncio
import hashlib
import json
import tarfile
from pathlib import Path

import httpx
from qdrant_client import QdrantClient

from app.config.settings import Settings
from app.services.database import connect


async def main(destination):
    settings = Settings()
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    connection = await connect(settings)
    try:
        rows = await connection.fetch(
            "SELECT raw_file_key,file_sha256 FROM registry.document_versions"
        )
        with tarfile.open(destination / "raw.tar.gz", "w:gz") as archive:
            for row in rows:
                path = (settings.raw_storage_path / row["raw_file_key"]).resolve()
                if not path.is_relative_to(settings.raw_storage_path.resolve()):
                    raise ValueError("Invalid original key")
                if hashlib.sha256(path.read_bytes()).hexdigest() != row["file_sha256"]:
                    raise ValueError("Original checksum mismatch")
                archive.add(path, arcname=row["raw_file_key"], recursive=False)
        manifest = json.loads((settings.index_storage_path / "index-manifest.json").read_text())
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value() or None,
            check_compatibility=False,
        )
        try:
            snapshot = client.create_snapshot(manifest["collection"], wait=True)
            headers = (
                {"api-key": settings.qdrant_api_key.get_secret_value()}
                if settings.qdrant_api_key.get_secret_value()
                else {}
            )
            async with httpx.AsyncClient(timeout=120, trust_env=False, headers=headers) as http:
                response = await http.get(
                    settings.qdrant_url
                    + "/collections/"
                    + manifest["collection"]
                    + "/snapshots/"
                    + snapshot.name
                )
                response.raise_for_status()
                (destination / "qdrant.snapshot").write_bytes(response.content)
        finally:
            client.close()
        with tarfile.open(destination / "configuration.tar.gz", "w:gz") as archive:
            archive.add("config", arcname="config")
            archive.add(
                settings.index_storage_path / "index-manifest.json", arcname="index-manifest.json"
            )
            archive.add(
                settings.index_storage_path / "models/manifest.json", arcname="model-manifest.json"
            )
        pipeline_files = []
        for directory in ("registered", "chunks"):
            location = settings.index_storage_path / directory
            if location.exists():
                pipeline_files.extend(p for p in location.rglob("*.json") if p.is_file())
        for name in ("corpus-manifest.json", "parsing-final-report.json"):
            location = settings.index_storage_path / name
            if location.exists():
                pipeline_files.append(location)
        pipeline_hashes = {}
        with tarfile.open(destination / "pipeline.tar.gz", "w:gz") as archive:
            for path in sorted(pipeline_files):
                key = str(path.relative_to(settings.index_storage_path)).replace("\\", "/")
                pipeline_hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
                archive.add(path, arcname=key, recursive=False)
        report = {
            "documents": len(rows),
            "fingerprint": manifest["fingerprint"],
            "collection": manifest["collection"],
            "points": manifest["chunks"],
            "originals": {r["raw_file_key"]: r["file_sha256"] for r in rows},
            "pipeline_artifacts": pipeline_hashes,
            "files": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in destination.iterdir()
                if p.is_file()
                and p.name
                in {
                    "postgres.dump",
                    "raw.tar.gz",
                    "configuration.tar.gz",
                    "pipeline.tar.gz",
                    "qdrant.snapshot",
                }
            },
            "secrets": "Not included; preserve local .env separately",
        }
        (destination / "backup-manifest.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps({"backup_documents": len(rows), "points": manifest["chunks"]}), flush=True)
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    asyncio.run(main(parser.parse_args().destination))
