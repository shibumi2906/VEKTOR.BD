"""Local pinned ONNX encoders. No inference service and no remote model code."""

import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


class LocalModel:
    def __init__(self, spec, root=Path("data/models"), max_length=None):
        self.spec = spec
        self.max_length = max_length or spec["max_length"]
        path = root / spec["name"]
        manifest = json.loads((root / "manifest.json").read_text("utf-8"))
        for file in ("tokenizer.json", spec["onnx"]):
            expected = next(
                r
                for r in manifest
                if r["model"] == spec["model"]
                and r["revision"] == spec["revision"]
                and r["file"].replace("\\", "/").endswith("/" + spec["name"] + "/" + file)
            )
            if hashlib.sha256((path / file).read_bytes()).hexdigest() != expected["sha256"]:
                raise ValueError("Local model checksum mismatch")
        self.tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
        self.tokenizer.no_truncation()
        pad_id = self.tokenizer.token_to_id("<pad>")
        if pad_id is None:
            pad_id = self.tokenizer.token_to_id("[PAD]")
        if pad_id is None:
            raise ValueError("Model has no known padding token")
        self.tokenizer.enable_padding(pad_id=pad_id)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(path / spec["onnx"]), options, providers=["CPUExecutionProvider"]
        )

    def count(self, text):
        return len(self.tokenizer.encode(text).ids)

    def inputs(self, texts):
        encoded = self.tokenizer.encode_batch(texts)
        if any(len(item.ids) > self.max_length for item in encoded):
            raise ValueError("Model token limit exceeded; re-chunk before embedding")
        available = {i.name for i in self.session.get_inputs()}
        result = {
            "input_ids": np.asarray([e.ids for e in encoded], dtype=np.int64),
            "attention_mask": np.asarray([e.attention_mask for e in encoded], dtype=np.int64),
            "token_type_ids": np.asarray([e.type_ids for e in encoded], dtype=np.int64),
        }
        return {k: v for k, v in result.items() if k in available}

    def encode(self, texts, query=False, batch_size=8):
        prefix = self.spec["query_prefix"] if query else self.spec["document_prefix"]
        vectors = []
        for offset in range(0, len(texts), batch_size):
            feed = self.inputs([prefix + t for t in texts[offset : offset + batch_size]])
            output = self.session.run(None, feed)[0]
            if output.ndim == 3:
                mask = feed["attention_mask"][..., None]
                output = (output * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
            output = output.astype(np.float32)
            output /= np.linalg.norm(output, axis=1, keepdims=True).clip(min=1e-12)
            if output.shape[1] != self.spec["dimension"] or not np.isfinite(output).all():
                raise ValueError("Invalid embedding output")
            vectors.extend(output)
        return np.asarray(vectors, dtype=np.float32)

    def rank(self, query, texts):
        # Pair truncation is explicit for reranking only; source quotes are never truncated.
        self.tokenizer.enable_truncation(max_length=self.max_length, strategy="only_second")
        try:
            scores = []
            for offset in range(0, len(texts), 8):
                feed = self.inputs([(query, t) for t in texts[offset : offset + 8]])
                logits = self.session.run(None, feed)[0].reshape(-1)
                scores.extend(logits.tolist())
            return np.asarray(scores)
        finally:
            self.tokenizer.no_truncation()
