"""Verify isolated PG/Qdrant restore and archived originals, then remove scratch targets."""

import argparse
import asyncio
import hashlib
import json
import re
import tarfile
import tempfile
from pathlib import Path

import httpx
from qdrant_client import QdrantClient

from app.config.settings import Settings
from app.services.database import connect


async def main(destination, database):
    if not re.fullmatch(r"pinui_restore_[0-9]+", database):
        raise ValueError("Only dedicated restore databases are allowed")
    settings = Settings()
    root = Path(destination)
    manifest = json.loads((root / "backup-manifest.json").read_text())
    for name, sha in manifest["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != sha:
            raise ValueError("Backup checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="pinui-restore-") as scratch:
        with tarfile.open(root / "raw.tar.gz") as archive:
            archive.extractall(scratch, filter="data")
        for key, sha in manifest["originals"].items():
            original = (Path(scratch) / key).resolve()
            if not original.is_relative_to(Path(scratch).resolve()):
                raise ValueError("Unsafe restore path")
            if hashlib.sha256(original.read_bytes()).hexdigest() != sha:
                raise ValueError("Restored original mismatch")
        if manifest.get("pipeline_artifacts"):
            pipeline_root = Path(scratch) / "pipeline"
            pipeline_root.mkdir()
            with tarfile.open(root / "pipeline.tar.gz") as archive:
                archive.extractall(pipeline_root, filter="data")
            for key, sha in manifest["pipeline_artifacts"].items():
                artifact = (pipeline_root / key).resolve()
                if not artifact.is_relative_to(pipeline_root.resolve()):
                    raise ValueError("Unsafe pipeline restore path")
                if hashlib.sha256(artifact.read_bytes()).hexdigest() != sha:
                    raise ValueError("Restored pipeline artifact mismatch")
    from pydantic import SecretStr

    restored = settings.model_copy(
        update={
            "postgres_url": SecretStr(
                settings.postgres_url.get_secret_value().rsplit("/", 1)[0] + "/" + database
            )
        }
    )
    connection = await connect(restored)
    collection = database
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() or None,
        check_compatibility=False,
    )
    try:
        assert (
            await connection.fetchval("SELECT count(*) FROM registry.document_versions")
            == manifest["documents"]
        )
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM registry.generation_chunks g "
                "JOIN registry.index_generations i USING(generation_id) WHERE i.status='active'"
            )
            == manifest["points"]
        )
        fingerprints = await connection.fetch(
            "SELECT DISTINCT fingerprint FROM registry.index_generations WHERE status='active'"
        )
        assert [r["fingerprint"] for r in fingerprints] == [manifest["fingerprint"]]
        headers = (
            {"api-key": settings.qdrant_api_key.get_secret_value()}
            if settings.qdrant_api_key.get_secret_value()
            else {}
        )
        async with httpx.AsyncClient(timeout=120, trust_env=False, headers=headers) as http:
            with (root / "qdrant.snapshot").open("rb") as snapshot:
                response = await http.post(
                    settings.qdrant_url
                    + "/collections/"
                    + collection
                    + "/snapshots/upload?wait=true&priority=snapshot",
                    files={"snapshot": snapshot},
                )
                response.raise_for_status()
        assert client.count(collection, exact=True).count == manifest["points"]
        points, offset = [], None
        while True:
            batch, offset = client.scroll(
                collection, limit=256, offset=offset, with_payload=True, with_vectors=True
            )
            points.extend(batch)
            if offset is None:
                break
        for point in points:
            old = client.retrieve(
                manifest["collection"], [point.id], with_payload=True, with_vectors=True
            )[0]
            if point.payload != old.payload or point.vector != old.vector:
                raise ValueError("Restored Qdrant fingerprint mismatch")
        result = {
            "postgres": "passed",
            "raw": "passed",
            "configuration": "passed",
            "pipeline_artifacts": len(manifest.get("pipeline_artifacts", {})),
            "qdrant": "passed",
            "points": len(points),
            "fingerprint": manifest["fingerprint"],
        }
        (root / "restore-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
    finally:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.close()
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    parser.add_argument("database")
    args = parser.parse_args()
    asyncio.run(main(args.destination, args.database))
