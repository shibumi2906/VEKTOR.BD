"""Deterministic structural chunks and exact spans into immutable extracted text."""

import hashlib
import re
from collections import Counter
from uuid import UUID, uuid5

from app.registry.legal_engine import canonical_hash

TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
CLAUSE = re.compile(r'^\s*((?:\d{1,2}\.)|(?:\d{1,2}(?:\.\d{1,2}){1,3})\.?)\s+(?=[א-ת"״])')
PARSER_REVISION = "pdf-text-structural-v3"
CHUNKER_REVISION = "structural-spans-v1"


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def header_key(line):
    return re.sub(r"\d+", "#", " ".join(line.split()))


def parse_pages(document_id, pages, parser_fingerprint, non_content_pages=()):
    revision = str(uuid5(UUID(document_id), parser_fingerprint))
    edges = Counter()
    for page in pages:
        lines = [line for line in page.splitlines() if line.strip()]
        # Only repetitive contact lines and page labels qualify, never arbitrary repeated clauses.
        candidates = lines[:5] + lines[-3:]
        edges.update(
            set(
                header_key(line)
                for line in candidates
                if re.search(r"@|www\.|כתובת|טלפון|טל\s*\d|עמוד\s+\d+\s+מתוך", line)
            )
        )
    repeated = {key for key, count in edges.items() if count >= 3}
    blocks, page_quality = [], []
    current_clause = None
    group = 0
    for page_index, text in enumerate(pages):
        hebrew = len(re.findall("[א-ת]", text))
        if page_index + 1 in non_content_pages:
            quality = "reviewed_non_content"
        elif hebrew < 20 or "\ufffd" in text or "\x00" in text:
            quality = "ocr_required"
        else:
            quality = "text_layer"
        page_quality.append({"page": page_index + 1, "quality": quality, "hebrew_chars": hebrew})
        boundaries = []
        cursor = 0
        nonempty_lines = [line for line in text.splitlines() if line.strip()]
        edge_lines = set(nonempty_lines[:5] + nonempty_lines[-3:])
        for line in text.splitlines(keepends=True):
            label = None
            match = CLAUSE.match(line)
            noncontent = quality != "text_layer" or (
                line.rstrip("\r\n") in edge_lines and header_key(line) in repeated
            )
            if line.strip() == str(page_index + 1) and line.rstrip("\r\n") in edge_lines:
                noncontent = True
            if match and not noncontent:
                label = match.group(1).rstrip(".")
            if label or noncontent:
                boundaries.append((cursor, label, noncontent))
                if noncontent:
                    boundaries.append((cursor + len(line), None, False))
            cursor += len(line)
        boundaries.append((len(text), None, False))
        boundaries.insert(0, (0, None, quality != "text_layer"))
        # Last declaration at an offset wins, except clause labels are retained.
        merged = {}
        for offset, label, excluded in boundaries:
            previous = merged.get(offset)
            merged[offset] = (label or (previous[0] if previous else None), excluded)
        positions = sorted(merged)
        for start, end in zip(positions, positions[1:], strict=False):
            if not text[start:end].strip():
                continue
            label, excluded = merged[start]
            if label:
                current_clause = label
                group += 1
            elif not current_clause and not excluded:
                group += 1
            value = text[start:end]
            block_id = str(uuid5(UUID(revision), f"{page_index}:{start}:{end}:{digest(value)}"))
            blocks.append(
                {
                    "block_id": block_id,
                    "ordinal": len(blocks),
                    "original_text": value,
                    "search_text": value,
                    "normalization_map": "identity-v1",
                    "locator": {
                        "pdf_page_index": page_index,
                        "displayed_page": page_index + 1,
                        "printed_page_number": None,
                        "paragraph_id": None,
                        "bbox": None,
                        "page_char_start": start,
                        "page_char_end": end,
                    },
                    "clause": current_clause if not excluded else None,
                    "section": current_clause.split(".")[0]
                    if current_clause and not excluded
                    else None,
                    "group": group,
                    "excluded": excluded,
                    "structure_confidence": "medium" if current_clause and not excluded else "low",
                }
            )
        if quality != "text_layer":
            current_clause = None
            group += 1
    return revision, blocks, page_quality


def create_chunks(document, revision, blocks, config):
    from app.chunking.tokenizer import scanner

    tokenizer = scanner(config)
    maximum, overlap = config["max_tokens"], config["overlap_tokens"]
    if not 0 <= overlap < maximum:
        raise ValueError("Overlap must be smaller than positive token limit")
    fingerprint = canonical_hash(
        {
            "revision": CHUNKER_REVISION,
            "tokenizer": config["tokenizer"],
            "max_tokens": maximum,
            "overlap_tokens": overlap,
            "normalization": "identity-v1",
        }
    )
    groups = {}
    for block in blocks:
        if not block["excluded"]:
            groups.setdefault(block["group"], []).append(block)
    chunks = []
    for group_blocks in groups.values():
        source = ""
        mapping = []
        for block in group_blocks:
            if source:
                source += "\n"
            start = len(source)
            source += block["original_text"]
            mapping.append((start, len(source), block))
        tokens = list(tokenizer.finditer(source))
        if not tokens:
            continue
        token_start, part = 0, 1
        while token_start < len(tokens):
            token_end = min(token_start + maximum, len(tokens))
            start = 0 if token_start == 0 else tokens[token_start].start()
            end = len(source) if token_end == len(tokens) else tokens[token_end].start()
            text = source[start:end]
            while len(tokenizer.findall(text)) > maximum:
                token_end -= 1
                if token_end <= token_start + overlap:
                    raise ValueError("Tokenizer cannot split this block without losing coverage")
                end = tokens[token_end].start()
                text = source[start:end]
            spans = []
            for block_start, block_end, block in mapping:
                left, right = max(start, block_start), min(end, block_end)
                if left < right:
                    spans.append(
                        {
                            "block_id": block["block_id"],
                            "start": left - block_start,
                            "end": right - block_start,
                            "chunk_start": left - start,
                            "chunk_end": right - start,
                            "locator": block["locator"],
                        }
                    )
            content_sha = digest(text)
            chunk_id = str(
                uuid5(
                    UUID(document["document_id"]),
                    canonical_hash(
                        [revision, fingerprint, [s["block_id"] for s in spans], part, content_sha]
                    ),
                )
            )
            chunks.append(
                {
                    **document,
                    "chunk_id": chunk_id,
                    "parsing_revision": revision,
                    "chunking_fingerprint": fingerprint,
                    "index_generation_id": None,
                    "section": group_blocks[0]["section"],
                    "clause": group_blocks[0]["clause"],
                    "part": part,
                    "structure_confidence": group_blocks[0]["structure_confidence"],
                    "text": text,
                    "content_sha256": content_sha,
                    "spans": spans,
                    "token_count": len(tokenizer.findall(text)),
                    "tokenizer": config["tokenizer"],
                    **(
                        {"tokenizer_model_name": config["tokenizer_model_name"]}
                        if config.get("tokenizer_model_name")
                        else {}
                    ),
                    "overlap_tokens": overlap if part > 1 else 0,
                    "quality_status": "staged_unreviewed",
                    "current_norms_eligible": False,
                }
            )
            if token_end == len(tokens):
                break
            token_start = token_end - overlap
            part += 1
    return fingerprint, chunks


def verify_chunks(blocks, chunks, maximum):
    from app.chunking.tokenizer import scanner

    lookup = {block["block_id"]: block for block in blocks}
    coverage = {key: [] for key, block in lookup.items() if not block["excluded"]}
    seen = set()
    for chunk in chunks:
        if chunk["chunk_id"] in seen:
            raise ValueError("Duplicate chunk")
        seen.add(chunk["chunk_id"])
        if digest(chunk["text"]) != chunk["content_sha256"]:
            raise ValueError("Chunk hash mismatch")
        if (
            chunk["token_count"] != len(scanner(chunk).findall(chunk["text"]))
            or not 0 < chunk["token_count"] <= maximum
        ):
            raise ValueError("Chunk token count invalid")
        cited_positions = set()
        for span in chunk["spans"]:
            block = lookup[span["block_id"]]
            start, end = span["start"], span["end"]
            if not 0 <= start < end <= len(block["original_text"]) or block["excluded"]:
                raise ValueError("Invalid source span")
            if (
                chunk["text"][span["chunk_start"] : span["chunk_end"]]
                != block["original_text"][start:end]
            ):
                raise ValueError("Source text mismatch")
            if span["locator"] != block["locator"]:
                raise ValueError("Source locator mismatch")
            if not 0 <= span["chunk_start"] < span["chunk_end"] <= len(chunk["text"]):
                raise ValueError("Invalid chunk span")
            cited_positions.update(range(span["chunk_start"], span["chunk_end"]))
            coverage[block["block_id"]].append((start, end))
        if any(
            i not in cited_positions for i, char in enumerate(chunk["text"]) if not char.isspace()
        ):
            raise ValueError("Uncited chunk text")
    for key, intervals in coverage.items():
        text = lookup[key]["original_text"]
        covered = set()
        for start, end in intervals:
            covered.update(range(start, end))
        if any(i not in covered for i, char in enumerate(text) if not char.isspace()):
            raise ValueError("Uncovered source text")
    return {"chunks": len(chunks), "blocks": len(blocks), "integrity": "passed"}


def verify_artifact(artifact):
    """Reconstruct blocks from full page text and bind every chunk to its document."""
    revision = UUID(artifact["parsing_revision"])
    document_id = UUID(artifact["document"]["document_id"])
    if revision != uuid5(document_id, artifact["parser_fingerprint"]):
        raise ValueError("Parsing identity mismatch")
    if artifact["document"].get("document_type") == "docx":
        for ordinal, block in enumerate(artifact["blocks"]):
            paragraph = block["locator"]["paragraph_id"]
            if (
                block["ordinal"] != ordinal
                or block["original_text"] != artifact["paragraphs"][paragraph]
            ):
                raise ValueError("DOCX paragraph mismatch")
            if block["locator"]["pdf_page_index"] is not None:
                raise ValueError("DOCX cannot have invented PDF pages")
            if block["block_id"] != str(
                uuid5(revision, paragraph + ":" + digest(block["original_text"]))
            ):
                raise ValueError("DOCX block identity mismatch")
    else:
        page_coverage = [set() for _ in artifact["pages"]]
        for ordinal, block in enumerate(artifact["blocks"]):
            locator = block["locator"]
            page = locator["pdf_page_index"]
            start, end = locator["page_char_start"], locator["page_char_end"]
            if block["ordinal"] != ordinal or not 0 <= page < len(page_coverage):
                raise ValueError("Block order or page mismatch")
            text = artifact["pages"][page]
            if not 0 <= start < end <= len(text) or block["original_text"] != text[start:end]:
                raise ValueError("Block differs from extracted original page")
            expected_id = str(
                uuid5(revision, f"{page}:{start}:{end}:{digest(block['original_text'])}")
            )
            if block["block_id"] != expected_id or locator["displayed_page"] != page + 1:
                raise ValueError("Block identity or displayed page mismatch")
            if page_coverage[page].intersection(range(start, end)):
                raise ValueError("Overlapping original blocks")
            page_coverage[page].update(range(start, end))
        for page, text in enumerate(artifact["pages"]):
            if any(
                i not in page_coverage[page] for i, char in enumerate(text) if not char.isspace()
            ):
                raise ValueError("Unrecorded page text")
    for chunk in artifact["chunks"]:
        for key, value in artifact["document"].items():
            if chunk.get(key) != value:
                raise ValueError("Chunk document metadata mismatch")
        if chunk["parsing_revision"] != str(revision):
            raise ValueError("Chunk revision mismatch")
        if chunk["chunking_fingerprint"] != artifact["chunking_fingerprint"]:
            raise ValueError("Chunk configuration mismatch")
        expected_id = str(
            uuid5(
                document_id,
                canonical_hash(
                    [
                        str(revision),
                        artifact["chunking_fingerprint"],
                        [s["block_id"] for s in chunk["spans"]],
                        chunk["part"],
                        chunk["content_sha256"],
                    ]
                ),
            )
        )
        if chunk["chunk_id"] != expected_id:
            raise ValueError("Chunk identity mismatch")
    return verify_chunks(artifact["blocks"], artifact["chunks"], artifact["max_tokens"])
