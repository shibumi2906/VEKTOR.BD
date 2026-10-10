import os
from functools import lru_cache
from pathlib import Path

from tokenizers import Tokenizer


class Offset:
    def __init__(self, start, end):
        self.left, self.right = start, end

    def start(self):
        return self.left

    def end(self):
        return self.right


class ModelScanner:
    def __init__(self, name):
        root = Path(os.environ.get("MODEL_STORAGE_PATH", "data/models"))
        self.tokenizer = Tokenizer.from_file(str(root / name / "tokenizer.json"))
        self.tokenizer.no_padding()
        self.tokenizer.no_truncation()

    def finditer(self, text):
        return [
            Offset(a, b) for a, b in self.tokenizer.encode(text, add_special_tokens=False).offsets
        ]

    def findall(self, text):
        return self.tokenizer.encode(text, add_special_tokens=False).ids


@lru_cache(maxsize=3)
def model_scanner(name):
    return ModelScanner(name)


def scanner(config):
    if config.get("tokenizer_model_name"):
        return model_scanner(config["tokenizer_model_name"])
    from app.chunking.core import TOKEN

    return TOKEN
