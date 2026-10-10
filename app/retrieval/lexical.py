"""Stable lexical dimensions; IDF is applied once by Qdrant, never by this encoder."""

import re
import unicodedata
from collections import Counter


def tokens(text):
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKC", text).casefold()
        if not ("\u0591" <= char <= "\u05c7" and unicodedata.category(char) == "Mn")
    )
    return re.findall(r"\d+(?:\.\d+)*|[^\W\d_]+", normalized)


def sparse(text, vocabulary, average_length, query=False):
    counts = Counter(tokens(text))
    length = sum(counts.values())
    result = []
    for token, count in counts.items():
        if token in vocabulary:
            # BM25 term saturation and length normalization; Qdrant owns corpus IDF.
            weight = (
                1.0
                if query
                else count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / average_length))
            )
            result.append((vocabulary[token], weight))
    result.sort()
    return {"indices": [i for i, _ in result], "values": [v for _, v in result]}
