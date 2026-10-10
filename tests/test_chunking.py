import copy
from uuid import NAMESPACE_URL, uuid5

import pytest

from app.chunking.core import create_chunks, parse_pages, verify_chunks

DOCUMENT = {"document_id": str(uuid5(NAMESPACE_URL, "synthetic-hebrew-document"))}
CONFIG = {"max_tokens": 800, "overlap_tokens": 100, "tokenizer": "unicode-word-punctuation-v1"}
HEBREW = "הסכם התחדשות עירונית וזכויות בעלי הדירות. "


def build(pages, config=None, reviewed=()):
    revision, blocks, quality = parse_pages(DOCUMENT["document_id"], pages, "a" * 64, reviewed)
    fingerprint, chunks = create_chunks(DOCUMENT, revision, blocks, config or CONFIG)
    verify_chunks(blocks, chunks, (config or CONFIG)["max_tokens"])
    return revision, blocks, chunks, quality, fingerprint


def test_clause_continues_across_pages_with_exact_spans():
    _, blocks, chunks, _, _ = build(["12.5.1. " + HEBREW * 4, HEBREW * 4 + "\n12.5.2. " + HEBREW])
    assert len(chunks) == 2
    assert chunks[0]["clause"] == "12.5.1"
    assert {s["locator"]["pdf_page_index"] for s in chunks[0]["spans"]} == {0, 1}
    assert all(b["normalization_map"] == "identity-v1" for b in blocks)


def test_short_clause_not_split_and_neighbour_not_merged():
    _, _, chunks, _, _ = build(["1.1 " + HEBREW + "\n1.2 " + HEBREW])
    assert [c["clause"] for c in chunks] == ["1.1", "1.2"]
    assert all(c["part"] == 1 for c in chunks)


def test_long_clause_limit_overlap_and_full_coverage():
    cfg = {**CONFIG, "max_tokens": 30, "overlap_tokens": 6}
    _, blocks, chunks, _, _ = build(["3.1 " + HEBREW * 40], cfg)
    assert len(chunks) > 2
    assert all(c["clause"] == "3.1" and c["token_count"] <= 30 for c in chunks)
    assert chunks[1]["spans"][0]["start"] < chunks[0]["spans"][0]["end"]
    verify_chunks(blocks, chunks, 30)


def test_no_overlap_between_different_clauses():
    cfg = {**CONFIG, "max_tokens": 30, "overlap_tokens": 6}
    _, _, chunks, _, _ = build(["1.1 " + HEBREW * 20 + "\n1.2 " + HEBREW], cfg)
    assert next(c for c in chunks if c["clause"] == "1.2")["overlap_tokens"] == 0


def test_repeatable_ids_and_fingerprint_changes_with_parameters():
    pages = ["2.1 " + HEBREW * 6]
    assert build(pages) == build(pages)
    a, _, chunks_a, _, fp_a = build(pages)
    b, _, chunks_b, _, fp_b = build(pages, {**CONFIG, "overlap_tokens": 50})
    assert a == b and fp_a != fp_b
    assert chunks_a[0]["chunk_id"] != chunks_b[0]["chunk_id"]


def test_dates_footnotes_and_financial_values_not_clause_labels_or_lost():
    page = "1. " + HEBREW + "\n04.2025 " + HEBREW + "\n1 " + HEBREW + "\n120000\n" + HEBREW
    _, _, chunks, _, _ = build([page])
    assert len(chunks) == 1 and chunks[0]["clause"] == "1"
    assert "120000" in chunks[0]["text"] and "04.2025" in chunks[0]["text"]


def test_repeated_contact_headers_preserved_in_blocks_excluded_from_chunks():
    pages = ["בית הדפוס12 טל074-1234567\n" + f"{i}.1 " + HEBREW * 4 for i in range(1, 4)]
    _, blocks, chunks, _, _ = build(pages)
    assert any(b["excluded"] and "בית הדפוס" in b["original_text"] for b in blocks)
    assert all("בית הדפוס" not in c["text"] for c in chunks)


def test_weak_text_page_needs_ocr_and_is_not_successfully_chunked():
    _, blocks, chunks, quality, _ = build([HEBREW * 3, "unreadable scan"])
    assert quality[1]["quality"] == "ocr_required"
    assert all(s["locator"]["pdf_page_index"] == 0 for c in chunks for s in c["spans"])
    assert any(b["excluded"] for b in blocks)


def test_reviewed_blank_page_is_explicitly_recorded():
    _, _, chunks, quality, _ = build([HEBREW * 3, ""], reviewed=[2])
    assert quality[1]["quality"] == "reviewed_non_content"
    assert len(chunks) == 1


@pytest.mark.parametrize("damage", ["text", "span", "locator", "coverage", "duplicate"])
def test_verification_rejects_corruption(damage):
    _, blocks, chunks, _, _ = build(["1.1 " + HEBREW * 4])
    chunks = copy.deepcopy(chunks)
    if damage == "text":
        chunks[0]["text"] += "X"
    elif damage == "span":
        chunks[0]["spans"][0]["end"] = 999999
    elif damage == "locator":
        chunks[0]["spans"][0]["locator"]["pdf_page_index"] = 100
    elif damage == "coverage":
        chunks.clear()
    else:
        chunks.append(copy.deepcopy(chunks[0]))
    with pytest.raises(ValueError):
        verify_chunks(blocks, chunks, 800)


def test_invalid_size_rejected():
    with pytest.raises(ValueError):
        build([HEBREW], {**CONFIG, "max_tokens": 100, "overlap_tokens": 100})
