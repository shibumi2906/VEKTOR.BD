"""Extract and stage Hebrew corpus chunks; never activates a search index."""

import argparse
import hashlib
import json
from pathlib import Path

import pypdf
from pypdf import PdfReader

from app.chunking.core import (
    PARSER_REVISION,
    create_chunks,
    parse_pages,
    verify_artifact,
    verify_chunks,
)
from app.registry.corpus import identity
from app.registry.legal_engine import canonical_hash
from app.registry.policy import validate_current_policy


def build(workspace):
    manifest = json.loads((workspace / "data/corpus-manifest.json").read_text("utf-8"))
    config = json.loads((workspace / "config/chunking.json").read_text("utf-8"))
    validate_current_policy(manifest)
    destination = workspace / "data/chunks"
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for row in manifest["documents"]:
        if row["download_status"] != "downloaded":
            continue
        if row["artifact_kind"] == "consolidated_law":
            raise ValueError("Law chunks require the legal snapshot adapter, not a raw PDF")
        path = (workspace / row["file"]).resolve()
        if not path.is_relative_to((workspace / "data/raw").resolve()):
            raise ValueError("Original outside raw storage")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Original hash mismatch")
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted original")
        pages = [page.extract_text() or "" for page in reader.pages]
        if len(pages) != row["pdf_validation"]["pages"]:
            raise ValueError("Original page count mismatch")
        reviewed = config["reviewed_non_content_pages"].get(row["download_id"], [])
        parser = canonical_hash(
            {
                "parser": PARSER_REVISION,
                "pypdf": pypdf.__version__,
                "reviewed_non_content_pages": reviewed,
            }
        )
        document_id = str(identity("document:" + row["download_id"] + ":" + row["sha256"]))
        document = {
            "document_id": document_id,
            "document_family_id": str(identity("family:" + row["download_id"])),
            "project_id": None,
            "title": row["title"],
            "document_alias": row["download_id"],
            "file_sha256": row["sha256"],
            "version_label": row.get("version_label"),
            "document_type": "pdf",
            "document_role": row["document_role"],
            "version_status": row["version_status"],
            "legal_status": row["legal_status"],
            "verification_status": row["verification_status"],
            "category": row["artifact_kind"],
            "language": row["language"],
            "source_id": row["source_id"],
            "source_url": row["url"],
        }
        revision, blocks, quality = parse_pages(document_id, pages, parser, reviewed)
        fingerprint, chunks = create_chunks(document, revision, blocks, config)
        checks = verify_chunks(blocks, chunks, config["max_tokens"])
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
            "checks": checks,
            "warnings": [
                "PDF table cell reconstruction not implemented",
                "Provisional tokenizer; embedding tokenizer must remeasure before indexing",
                "Text extraction order and structural labels require manual review",
            ],
            "max_tokens": config["max_tokens"],
        }
        verify_artifact(artifact)
        serialized = json.dumps(artifact, ensure_ascii=False, indent=2)
        serialized_sha = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        key = row["download_id"] + "-" + revision + "-" + serialized_sha[:16] + ".json"
        output = destination / key
        if output.exists():
            if output.read_text("utf-8") != serialized:
                raise ValueError("Immutable parsing artifact mismatch")
        else:
            temporary = output.with_suffix(".tmp")
            temporary.write_text(serialized, encoding="utf-8")
            temporary.replace(output)
        results.append(
            {
                "document_alias": row["download_id"],
                "artifact": key,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "pages": len(pages),
                **checks,
                "ocr_required_pages": [
                    q["page"] for q in quality if q["quality"] == "ocr_required"
                ],
                "reviewed_non_content_pages": reviewed,
                "numbered_chunks": sum(c["clause"] is not None for c in chunks),
            }
        )
    report = {"documents": results, "index_created": False, "chunks_activated": False}
    (destination / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "documents": len(results),
                "pages": sum(r["pages"] for r in results),
                "chunks": sum(r["chunks"] for r in results),
                "ocr_required_pages": sum(len(r["ocr_required_pages"]) for r in results),
                "integrity": "passed",
                "index_created": False,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--store", action="store_true", help="Also stage checked chunks in PostgreSQL"
    )
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    build(workspace)
    if args.store:
        import asyncio

        from scripts.chunk_registry import run

        asyncio.run(run(workspace))
