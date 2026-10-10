"""Conservative PDF table locators aligned to the immutable extracted page text.

Ambiguous/reordered cells are left unassigned and flagged for review. Geometry
never substitutes for an exact source range.
"""

import re
from uuid import UUID, uuid5

import pdfplumber

from app.chunking.core import digest


def unique_range(page_text, cell_text):
    positions = [i for i, char in enumerate(page_text) if not char.isspace()]
    compact = "".join(page_text[i] for i in positions)
    needle = re.sub(r"\s+", "", cell_text or "")
    if not needle:
        return None
    # Some PDF extractors return visual Hebrew order within words.
    candidates = {
        needle,
        re.sub(
            r"\s+",
            "",
            " ".join(
                word[::-1] if re.search("[א-ת]", word) else word
                for word in (cell_text or "").split()
            ),
        ),
    }
    matches = set()
    for candidate in candidates:
        offset = compact.find(candidate)
        if offset >= 0 and compact.find(candidate, offset + 1) < 0:
            matches.add((positions[offset], positions[offset + len(candidate) - 1] + 1))
    return next(iter(matches)) if len(matches) == 1 else None


def attach_tables(path, pages, revision, blocks, ocr_pages=()):
    cells, warnings = {}, []
    with pdfplumber.open(path) as document:
        for page_index, page in enumerate(document.pages):
            if page_index in ocr_pages:
                continue
            for table_index, table in enumerate(page.find_tables()):
                extracted = table.extract()
                for row_index, row in enumerate(table.rows):
                    for cell_index, bbox in enumerate(row.cells):
                        if bbox is None:
                            continue
                        span = unique_range(pages[page_index], extracted[row_index][cell_index])
                        if span is None:
                            warnings.append("PDF_TABLE_ALIGNMENT_REQUIRES_REVIEW")
                            continue
                        cells.setdefault(page_index, []).append(
                            {
                                "start": span[0],
                                "end": span[1],
                                "bbox": list(bbox),
                                "table_id": f"page{page_index + 1}-t{table_index + 1}",
                                "row_index": row_index,
                                "cell_index": cell_index,
                            }
                        )
    output = []
    group = max((b["group"] for b in blocks), default=0) + 1
    for block in blocks:
        locator = block["locator"]
        start, end = locator["page_char_start"], locator["page_char_end"]
        relevant = [
            c
            for c in cells.get(locator["pdf_page_index"], [])
            if start <= c["start"] < c["end"] <= end
        ]
        if any(
            a["start"] < b["end"] and b["start"] < a["end"]
            for i, a in enumerate(relevant)
            for b in relevant[i + 1 :]
        ):
            warnings.append("PDF_TABLE_ALIGNMENT_REQUIRES_REVIEW")
            output.append(block)
            continue
        cuts = sorted({start, end, *(c[k] for c in relevant for k in ("start", "end"))})
        for left, right in zip(cuts, cuts[1:], strict=False):
            value = pages[locator["pdf_page_index"]][left:right]
            copied = {
                **block,
                "locator": {**locator, "page_char_start": left, "page_char_end": right},
                "original_text": value,
                "search_text": value,
            }
            copied["block_id"] = str(
                uuid5(UUID(revision), f"{locator['pdf_page_index']}:{left}:{right}:{digest(value)}")
            )
            cell = next((c for c in relevant if c["start"] == left and c["end"] == right), None)
            if cell:
                copied["locator"].update(
                    {k: v for k, v in cell.items() if k not in ("start", "end")}
                )
                copied["group"] = group
                copied["structure_confidence"] = "low"
                group += 1
            copied["ordinal"] = len(output)
            output.append(copied)
    for ordinal, block in enumerate(output):
        block["ordinal"] = ordinal
    return output, sorted(set(warnings))
