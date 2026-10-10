"""Atomic, checksum-bound vector cache; interrupted or changed cache is regenerated."""

import hashlib
import json

import numpy as np


def load_cache(path, metadata_path, model):
    try:
        metadata = json.loads(metadata_path.read_text())
        if not isinstance(metadata, dict) or metadata["model"] != model:
            return {}
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["vectors_sha256"]:
            return {}
        vectors = np.load(path, allow_pickle=False)
        if (
            vectors.shape != (len(metadata["rows"]), model["dimension"])
            or not np.isfinite(vectors).all()
        ):
            return {}
        return {tuple(row): vector for row, vector in zip(metadata["rows"], vectors, strict=True)}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def save_cache(path, metadata_path, model, rows, vectors):
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as output:
        np.save(output, vectors, allow_pickle=False)
    sha = hashlib.sha256(temporary.read_bytes()).hexdigest()
    temporary.replace(path)
    metadata = {"model": model, "rows": rows, "vectors_sha256": sha}
    temporary = metadata_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata), encoding="utf-8")
    temporary.replace(metadata_path)
