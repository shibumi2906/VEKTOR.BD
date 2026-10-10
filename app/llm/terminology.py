"""Source-labelled vocabulary aids translation, never establishes legal obligations."""

import json
from pathlib import Path


def terminology(text):
    entries = json.loads(Path("config/terminology.json").read_text(encoding="utf-8"))
    folded = text.casefold()
    return [
        entry for entry in entries if any(alias.casefold() in folded for alias in entry["aliases"])
    ]
