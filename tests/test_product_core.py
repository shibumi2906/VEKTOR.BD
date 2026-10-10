import copy
import zipfile
from uuid import uuid4

import pytest

from app.chunking.core import create_chunks, verify_artifact
from app.config.settings import Settings
from app.models.query import QueryRequest
from app.parsing.docx import W, parse_docx
from app.retrieval.lexical import sparse, tokens
from app.services.errors import DomainError
from app.services.query import language, translate


def docx(tmp_path, numbering=""):
    path = tmp_path / "fixture.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            f'''<w:document xmlns:w="{W[1:-1]}"><w:body>
        <w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/>
</w:numPr></w:pPr><w:r><w:t>חניה</w:t></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>שטח</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        <w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/>
</w:numPr></w:pPr><w:r><w:t>ערבות</w:t></w:r></w:p>
        </w:body></w:document>''',
        )
        archive.writestr(
            "word/numbering.xml",
            numbering
            or f'''<w:numbering xmlns:w="{W[1:-1]}">
        <w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0">
<w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum>
        <w:num w:numId="1"><w:abstractNumId w:val="0"/>
<w:lvlOverride w:ilvl="0"><w:startOverride w:val="4"/></w:lvlOverride></w:num></w:numbering>''',
        )
    return path


def test_docx_body_order_numbering_table_and_integrity(tmp_path):
    identifier = str(uuid4())
    revision, parser, blocks, paragraphs, warnings = parse_docx(identifier, docx(tmp_path))
    assert [b["original_text"] for b in blocks] == ["חניה", "שטח", "ערבות"]
    assert [blocks[i]["clause"] for i in (0, 2)] == ["4", "5"]
    assert blocks[1]["locator"]["table_id"] == "t1"
    assert blocks[1]["locator"]["cell_index"] == 0
    assert all(b["locator"]["pdf_page_index"] is None for b in blocks)
    document = {"document_id": identifier, "document_type": "docx"}
    config = {"tokenizer": "unicode-v1", "max_tokens": 30, "overlap_tokens": 2}
    fingerprint, chunks = create_chunks(document, revision, blocks, config)
    artifact = {
        "document": document,
        "parsing_revision": revision,
        "parser_fingerprint": parser,
        "blocks": blocks,
        "paragraphs": paragraphs,
        "chunks": chunks,
        "chunking_fingerprint": fingerprint,
        "max_tokens": 30,
    }
    assert verify_artifact(artifact)["integrity"] == "passed"
    forged = copy.deepcopy(artifact)
    forged["chunks"][0]["document_id"] = str(uuid4())
    with pytest.raises(ValueError, match="metadata"):
        verify_artifact(forged)


def test_docx_rejects_entities(tmp_path):
    path = tmp_path / "entity.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", '<!DOCTYPE doc [<!ENTITY x "unsafe">]><doc/>')
    with pytest.raises(ValueError, match="entities"):
        parse_docx(str(uuid4()), path)


def test_sparse_niqqud_clause_numbers_and_stable_dimensions():
    assert tokens("חֲנָיָה 21.1") == ["חניה", "21.1"]
    vocabulary = {"חניה": 12, "21.1": 3}
    result = sparse("חֲנָיָה 21.1 חניה unknown", vocabulary, 5, query=True)
    assert result["indices"] == [3, 12]
    assert result["values"] == [1.0, 1.0]
    assert sparse("unknown", vocabulary, 5)["indices"] == []


async def test_translation_rejects_changed_dates():
    class Provider:
        async def structured(self, *args):
            return {"search_question_he": "חוזה 08.2026"}

    with pytest.raises(DomainError, match="TRANSLATION_UNAVAILABLE"):
        await translate(Provider(), "Договор 08.2025")


def test_languages_are_configurable():
    settings = Settings(
        _env_file=None, app_mode="bootstrap", supported_query_languages=["he", "ru", "en"]
    )
    assert language(QueryRequest(question="parking", language="auto"), settings) == "en"
    assert language(QueryRequest(question="חניה"), settings) == "he"
    assert language(QueryRequest(question="Парковка"), settings) == "ru"


def test_expansion_preserves_identifiers_and_is_bounded():
    from app.retrieval.expansion import expand_he

    question = "חניה ערבות שמאי סעיף 21.1 חוזה 08.2025"
    variants = expand_he(question, 2)
    assert len(variants) == 2
    assert all(v.startswith(question) for v in variants)
    assert expand_he(question, 1) == [question]


def test_alias_resolution_does_not_guess_between_projects():
    from app.registry.aliases import resolve

    family, project = uuid4(), uuid4()
    row = {
        "title": "Договор",
        "title_he": "חוזה",
        "version_label": "04.2025",
        "document_alias": "04.2025",
        "project_id": project,
        "family_id": family,
        "verification_status": "manual_review",
        "version_status": "unknown",
    }
    other = {**row, "project_id": uuid4(), "family_id": uuid4()}
    assert len(resolve([row, other], "  04.2025  ")) == 2
    assert resolve([row, other], "04.2025", project) == [row]
    current = {**row, "verification_status": "verified", "version_status": "current"}
    assert resolve([row, current], "04.2025") == [current]
    assert resolve([row], "") == []


def test_review_source_rejects_credentials_and_private_ip():
    from datetime import date

    from pydantic import ValidationError

    from app.models.review import DocumentReview

    body = {
        "file_sha256": "a" * 64,
        "version_status": "unknown",
        "legal_status": "unknown",
        "verification_status": "manual_review",
        "inventory_source_sha256": "b" * 64,
        "reviewed_through": date.today(),
        "notes": "Synthetic review source",
    }
    for url in ("http://127.0.0.1/", "https://localhost/", "https://user:secret@example.com/"):
        with pytest.raises(ValidationError):
            DocumentReview(**body, inventory_source_url=url)
    assert DocumentReview(**body, inventory_source_url="https://www.gov.il/")
