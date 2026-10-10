"""Download pinned official model files only; no remote Python or pickle execution."""

import hashlib
import json
from pathlib import Path

from huggingface_hub import hf_hub_download


def main():
    config = json.loads(Path("config/local-models.json").read_text("utf-8"))
    records = []
    for spec in [*config["candidates"], config["reranker"]]:
        root = Path("data/models") / spec["name"]
        for name in [
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "README.md",
            spec["onnx"],
        ]:
            path = Path(
                hf_hub_download(spec["model"], name, revision=spec["revision"], local_dir=root)
            )
            records.append(
                {
                    "model": spec["model"],
                    "revision": spec["revision"],
                    "file": str(path),
                    "size": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        print(json.dumps({"downloaded": spec["name"]}), flush=True)
    Path("data/models/manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
