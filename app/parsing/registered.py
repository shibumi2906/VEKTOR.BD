"""Parse an immutable registered original; unknown OCR quality blocks activation."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

import pypdf
from pypdf import PdfReader

from app.chunking.core import PARSER_REVISION, create_chunks, parse_pages, verify_artifact
from app.chunking.repository import stage_artifact
from app.parsing.docx import parse_docx
from app.parsing.layout import attach_tables
from app.parsing.ocr import attach_geometry, page_ocr
from app.registry.legal_engine import canonical_hash


async def parse_registered(connection, settings, document_id):
    row = await connection.fetchrow(
        """SELECT d.*,f.slug AS document_alias,f.project_id
        FROM registry.document_versions d JOIN registry.document_families f USING(family_id)
        WHERE document_id=$1""",
        UUID(str(document_id)),
    )
    if not row or row["category"] == "consolidated_law":
        raise ValueError("Registered non-law original required")
    root = settings.raw_storage_path.resolve()
    path = (root / row["raw_file_key"]).resolve()
    if (
        not path.is_relative_to(root)
        or hashlib.sha256(path.read_bytes()).hexdigest() != row["file_sha256"]
    ):
        raise ValueError("Original checksum mismatch")
    config = json.loads(Path("config/local-models.json").read_text())
    spec = config["selected"]
    chunk_config = {
        "tokenizer": spec["model"] + "@" + spec["revision"],
        "tokenizer_model_name": spec["name"],
        "max_tokens": spec["max_length"] - 32,
        "overlap_tokens": 16,
    }
    fields = (
        "document_id",
        "project_id",
        "title",
        "document_alias",
        "file_sha256",
        "version_label",
        "document_type",
        "document_role",
        "version_status",
        "legal_status",
        "verification_status",
        "category",
        "language",
        "source_id",
        "source_url",
    )
    document = {k: str(row[k]) if isinstance(row[k], UUID) else row[k] for k in fields}
    document["document_family_id"] = str(row["family_id"])
    pages, quality, paragraphs = [], [], None
    if row["document_type"] == "docx":
        revision, parser, blocks, paragraphs, warnings = parse_docx(str(document_id), path)
    else:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted original")
        pages = [p.extract_text() or "" for p in reader.pages]
        reviewed = json.loads(Path("config/chunking.json").read_text())[
            "reviewed_non_content_pages"
        ].get(row["document_alias"], [])
        parser = canonical_hash(
            {
                "parser": PARSER_REVISION,
                "pypdf": pypdf.__version__,
                "reviewed_non_content_pages": reviewed,
                "locator_metadata_version": 2,
                "table_geometry": "pdfplumber-0.11.10-exact-align-v1",
            }
        )
        revision, blocks, quality = parse_pages(str(document_id), pages, parser, reviewed)
        ocr_metadata = {}
        for q in quality:
            if q["quality"] == "ocr_required":
                index = q["page"] - 1
                pages[index], ocr_metadata[index] = page_ocr(path, index)
        if ocr_metadata:
            parser = canonical_hash({"base": parser, "ocr": settings.ocr_runtime_signature})
            revision, blocks, quality = parse_pages(str(document_id), pages, parser, reviewed)
            if any(q["quality"] == "ocr_required" for q in quality):
                raise ValueError("OCR_LOW_CONFIDENCE")
            for q in quality:
                if q["page"] - 1 in ocr_metadata:
                    q.update(ocr_metadata[q["page"] - 1])
        attach_geometry(blocks, ocr_metadata)
        blocks, warnings = attach_tables(path, pages, revision, blocks, ocr_metadata)
    fingerprint, chunks = create_chunks(document, revision, blocks, chunk_config)
    artifact = {
        "schema_version": 1,
        "document": document,
        "parsing_revision": revision,
        "parser_fingerprint": parser,
        "chunking_fingerprint": fingerprint,
        "pages": pages,
        "page_quality": quality,
        "blocks": blocks,
        "chunks": chunks,
        "warnings": warnings,
        "max_tokens": chunk_config["max_tokens"],
    }
    if paragraphs is not None:
        artifact["paragraphs"] = paragraphs
    verify_artifact(artifact)
    destination = settings.index_storage_path / "registered"
    destination.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(artifact, ensure_ascii=False)
    sha = hashlib.sha256(serialized.encode()).hexdigest()
    key = revision + "-" + sha + ".json"
    target = destination / key
    if target.exists() and target.read_text("utf-8") != serialized:
        raise ValueError("Immutable artifact conflict")
    target.write_text(serialized, encoding="utf-8")
    await stage_artifact(connection, artifact, "registered/" + key, sha)
    await connection.execute(
        """UPDATE registry.document_versions SET active_parsing_revision=$2,
        ingestion_status='parsed',page_count=$3 WHERE document_id=$1""",
        row["document_id"],
        UUID(revision),
        len(pages) if row["document_type"] == "pdf" else None,
    )
    return {
        "document_id": str(document_id),
        "blocks": len(blocks),
        "chunks": len(chunks),
        "parsing_revision": revision,
        "artifact": "registered/" + key,
        "sha256": sha,
    }
