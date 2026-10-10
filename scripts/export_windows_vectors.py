"""Export exact vectors/payloads instead of platform-dependent RocksDB snapshots."""

import gzip
import json
from pathlib import Path

from qdrant_client import QdrantClient

from app.config.settings import Settings


def main():
    settings = Settings()
    manifest = json.loads((settings.index_storage_path / "index-manifest.json").read_text())
    destination = Path("data/windows-build/seed-export")
    destination.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)
    try:
        collection = manifest["collection"]
        info = client.get_collection(collection)
        params = info.config.params.model_dump(mode="json", exclude_none=True)
        config = {"vectors": params["vectors"], "sparse_vectors": params["sparse_vectors"]}
        (destination / "vectors-config.json").write_text(json.dumps(config), encoding="utf-8")
        offset, count = None, 0
        with gzip.open(destination / "vectors.jsonl.gz", "wt", encoding="utf-8") as output:
            while True:
                points, offset = client.scroll(
                    collection, limit=128, offset=offset, with_vectors=True, with_payload=True
                )
                for point in points:
                    output.write(
                        json.dumps(
                            point.model_dump(mode="json", include={"id", "payload", "vector"}),
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                count += len(points)
                if offset is None:
                    break
        assert count == manifest["chunks"]
        print(json.dumps({"portable_vectors": count}))
    finally:
        client.close()


if __name__ == "__main__":
    main()
