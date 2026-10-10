"""Measured Hebrew retrieval on disjoint annotated clauses; frozen holdout after selection."""

import argparse
import gc
import json
import time
from pathlib import Path

import numpy as np

from app.chunking.core import create_chunks, verify_chunks
from app.embeddings.onnx import LocalModel


def corpus(spec):
    config = {
        "tokenizer": spec["model"] + "@" + spec["revision"],
        "tokenizer_model_name": spec["name"],
        "max_tokens": spec["max_length"] - 32,
        "overlap_tokens": 16,
    }
    chunks = []
    manifest = json.loads(Path("data/chunks/manifest.json").read_text())
    for row in manifest["documents"]:
        a = json.loads((Path("data/chunks") / row["artifact"]).read_text("utf-8"))
        _, values = create_chunks(a["document"], a["parsing_revision"], a["blocks"], config)
        verify_chunks(a["blocks"], values, config["max_tokens"])
        chunks.extend(values)
    return chunks, config


def cases(topics, split):
    result = []
    for alias, clause, questions in topics[split]:
        for question in questions:
            result.append({"question": question, "alias": alias, "clause": clause})
    return result


def measure(encoder, chunks, vectors, questions, reranker=None):
    queries = encoder.encode([q["question"] for q in questions], query=True)
    rows = []
    for question, query in zip(questions, queries, strict=True):
        # The chosen document is an explicit scope; other documents cannot supply the answer.
        allowed = [i for i, c in enumerate(chunks) if c["document_alias"] == question["alias"]]
        candidates = sorted(allowed, key=lambda i: float(vectors[i] @ query), reverse=True)[:30]
        if reranker:
            scores = reranker.rank(question["question"], [chunks[i]["text"] for i in candidates])
            candidates = [candidates[i] for i in np.argsort(-scores)]
        ranks = [
            rank
            for rank, index in enumerate(candidates, 1)
            if chunks[index]["clause"] == question["clause"]
        ]
        first = min(ranks) if ranks else None
        rows.append(
            {
                **question,
                "first_rank": first,
                "recall5": bool(first and first <= 5),
                "recall10": bool(first and first <= 10),
                "rr": 1 / first if first else 0,
            }
        )
    return {
        "cases": len(rows),
        "recall5": sum(r["recall5"] for r in rows) / len(rows),
        "recall10": sum(r["recall10"] for r in rows) / len(rows),
        "mrr": sum(r["rr"] for r in rows) / len(rows),
        "rows": rows,
    }


def main(split):
    root = Path("data/benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    config_path = Path("config/local-models.json")
    config = json.loads(config_path.read_text())
    topics = json.loads(Path("benchmarks/topics.json").read_text("utf-8"))
    assert set(tuple(t[:2]) for t in topics["dev"]).isdisjoint(
        tuple(t[:2]) for t in topics["holdout"]
    )
    specs = config["candidates"] if split == "dev" else [config["selected"]]
    if any(spec is None for spec in specs):
        raise ValueError("Select using dev results before opening holdout")
    results = []
    for spec in specs:
        chunks, chunk_config = corpus(spec)
        model = LocalModel(spec)
        cache = root / (spec["name"] + "-vectors.npy")
        started = time.monotonic()
        if cache.exists():
            vectors = np.load(cache)
            cached_chunks = json.loads((root / (spec["name"] + "-chunks.json")).read_text("utf-8"))
            if cached_chunks != chunks or len(vectors) != len(chunks):
                raise ValueError("Benchmark cache differs from current corpus")
        else:
            vectors = model.encode([c["text"] for c in chunks])
            np.save(cache, vectors)
        (root / (spec["name"] + "-chunks.json")).write_text(
            json.dumps(chunks, ensure_ascii=False), encoding="utf-8"
        )
        report = measure(model, chunks, vectors, cases(topics, split))
        results.append(
            {
                "spec": spec,
                "chunk_config": chunk_config,
                "variant": "dense",
                "seconds": time.monotonic() - started,
                **report,
            }
        )
        print(
            json.dumps(
                {
                    "model": spec["name"],
                    "variant": "dense",
                    "mrr": report["mrr"],
                    "recall10": report["recall10"],
                    "chunks": len(chunks),
                }
            ),
            flush=True,
        )
        for length in [256, 512] if split == "dev" else [config["reranker_length"]]:
            reranker = LocalModel(config["reranker"], max_length=length)
            report = measure(model, chunks, vectors, cases(topics, split), reranker)
            results.append(
                {
                    "spec": spec,
                    "chunk_config": chunk_config,
                    "variant": f"rerank-{length}",
                    **report,
                }
            )
            print(
                json.dumps(
                    {
                        "model": spec["name"],
                        "variant": f"rerank-{length}",
                        "mrr": report["mrr"],
                        "recall10": report["recall10"],
                    }
                ),
                flush=True,
            )
            del reranker
            gc.collect()
        del model
        gc.collect()
    output = root / (split + "-results.json")
    if output.exists():
        raise ValueError("Baseline already exists; archive explicitly before new experiment")
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if split == "dev":
        best = max(
            (r for r in results if r["variant"].startswith("rerank-")),
            key=lambda r: (r["mrr"], r["recall10"]),
        )
        config["selected"] = best["spec"]
        config["reranker_length"] = int(best["variant"].split("-")[1])
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("split", choices=["dev", "holdout"])
    main(parser.parse_args().split)
