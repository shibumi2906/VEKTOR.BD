"""Freeze rejection threshold using dev negatives; report separate holdout negatives."""

import json
from pathlib import Path

import numpy as np

from app.embeddings.onnx import LocalModel


def main():
    path = Path("config/local-models.json")
    config = json.loads(path.read_text())
    topics = json.loads(Path("benchmarks/topics.json").read_text("utf-8"))
    spec = config["selected"]
    root = Path("data/benchmarks")
    chunks = json.loads((root / (spec["name"] + "-chunks.json")).read_text("utf-8"))
    vectors = np.load(root / (spec["name"] + "-vectors.npy"))
    encoder = LocalModel(spec)
    reranker = LocalModel(config["reranker"], max_length=config["reranker_length"])
    report = {}
    for split in ("dev", "holdout"):
        values = []
        for question in topics["negative_" + split]:
            query = encoder.encode([question], query=True)[0]
            candidates = np.argsort(-(vectors @ query))[:30]
            score = float(max(reranker.rank(question, [chunks[i]["text"] for i in candidates])))
            values.append({"question": question, "max_score": score})
        if split == "dev":
            # Only dev influences the threshold. Holdout never changes it.
            threshold = max(v["max_score"] for v in values) + 0.1
            config["rerank_min_score"] = threshold
            path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        report[split] = {
            "rows": values,
            "false_accepts": sum(v["max_score"] >= threshold for v in values),
        }
    report["threshold"] = threshold
    report["limitations"] = (
        "Five out-of-domain negatives per split; near-domain absence needs review"
    )
    (root / "threshold-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"threshold": threshold, "holdout_false_accepts": report["holdout"]["false_accepts"]}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
