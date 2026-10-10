from uuid import UUID, uuid5

from app.models.legal import LegalResult
from app.services.errors import DomainError


async def original_block(connection, chunk, block_id):
    if chunk.get("legal_snapshot_sha256"):
        payload = await connection.fetchval(
            "SELECT payload FROM registry.legal_snapshots WHERE snapshot_sha256=$1",
            chunk["legal_snapshot_sha256"],
        )
        if not payload:
            raise DomainError("EVIDENCE_MISMATCH")
        snapshot = LegalResult.model_validate_json(payload)
        if snapshot.status != "verified" or snapshot.law_slug != chunk["document_alias"]:
            raise DomainError("EVIDENCE_MISMATCH")
        for clause in snapshot.clauses:
            expected = str(uuid5(UUID(chunk["parsing_revision"]), clause.clause_id))
            if block_id == expected and clause.clause_id == chunk["clause"]:
                return {
                    "original_text": clause.text_he,
                    "locator": {
                        "legal_clause_id": clause.clause_id,
                        "displayed_page": None,
                        "is_derived_text": True,
                    },
                    "provenance": [p.model_dump(mode="json") for p in clause.provenance],
                }
        raise DomainError("EVIDENCE_MISMATCH")
    return await connection.fetchrow(
        "SELECT original_text,locator FROM registry.blocks "
        "WHERE parsing_revision=$1 AND block_id=$2",
        UUID(chunk["parsing_revision"]),
        UUID(block_id),
    )


async def evidence(connection, candidates):
    result = []
    position = 0
    for chunk in candidates:
        metadata = (
            {"title": chunk["document_alias"], "version_label": chunk["as_of"]}
            if chunk.get("legal_snapshot_sha256")
            else await connection.fetchrow(
                "SELECT title,version_label FROM registry.document_versions WHERE document_id=$1",
                UUID(chunk["document_id"]),
            )
        )
        references = []
        for span in chunk["spans"]:
            position += 1
            row = await original_block(connection, chunk, span["block_id"])
            if row is None or not 0 <= span["start"] < span["end"] <= len(row["original_text"]):
                raise DomainError("EVIDENCE_MISMATCH")
            references.append(
                {
                    "evidence_id": f"E{position}",
                    "block_id": span["block_id"],
                    "span_start": span["start"],
                    "span_end": span["end"],
                    "quote": row["original_text"][span["start"] : span["end"]],
                    "locator": span["locator"],
                }
            )
        result.append(
            {
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "source_type": (
                    "template"
                    if chunk["category"] in {"model_agreement", "model_contract"}
                    else chunk["category"]
                ),
                "document_id": chunk["document_id"],
                "version_label": metadata.get("version_label") if metadata else None,
                "title": metadata.get("title") if metadata else None,
                "evidence_spans": references,
            }
        )
    return result


async def citation(connection, chunk, ref):
    if ref["chunk_id"] != chunk["chunk_id"]:
        raise DomainError("CITATION_SCOPE_MISMATCH", 502)
    start, end = ref["span_start"], ref["span_end"]
    if type(start) is not int or type(end) is not int:
        raise DomainError("INVALID_CITATION", 502)
    allowed = any(
        s["block_id"] == ref["block_id"] and s["start"] <= start < end <= s["end"]
        for s in chunk["spans"]
    )
    if not allowed:
        raise DomainError("CITATION_SCOPE_MISMATCH", 502)
    row = await original_block(connection, chunk, ref["block_id"])
    if row is None or end > len(row["original_text"]):
        raise DomainError("INVALID_CITATION", 502)
    if chunk.get("legal_snapshot_sha256"):
        provenance = row["provenance"]
        document = {
            "title": chunk["document_alias"],
            "issuer": provenance[-1]["issuer"],
            "source_url": provenance[-1]["url"],
            "source_name": "Проверенный сводный текст",
            "version_label": chunk["as_of"],
            "publication_date": None,
            "verification_status": "verified",
            "legal_status": "in_force",
            "document_role": "official",
            "category": "consolidated_law",
            "document_type": "legal_snapshot",
        }
    else:
        document = await connection.fetchrow(
            (
                "SELECT document_type,title,issuer,source_url,source_nam"
                "e,version_label,publication_date,verification_status,le"
                "gal_status,document_role,category FROM registry.documen"
                "t_versions WHERE document_id=$1"
            ),
            UUID(chunk["document_id"]),
        )
    identity = str(uuid5(UUID(ref["block_id"]), f"{start}:{end}"))
    return {
        "citation_id": identity,
        "document_id": chunk["document_id"],
        "chunk_id": chunk["chunk_id"],
        "block_id": ref["block_id"],
        "parsing_revision": chunk["parsing_revision"],
        "content_sha256": chunk["content_sha256"],
        "span_start": start,
        "span_end": end,
        "quote": row["original_text"][start:end],
        "locator": chunk["spans"][0]["locator"]
        if len(chunk["spans"]) == 1
        else next(s["locator"] for s in chunk["spans"] if s["block_id"] == ref["block_id"]),
        "section": chunk["section"],
        "clause": chunk["clause"],
        **{k: str(v) if v is not None else None for k, v in dict(document).items()},
        **(
            {
                "is_derived_text": True,
                "provenance": row["provenance"],
                "legal_snapshot_sha256": chunk["legal_snapshot_sha256"],
            }
            if chunk.get("legal_snapshot_sha256")
            else {}
        ),
    }


async def search_citations(connection, chunks):
    result, seen = [], set()
    for chunk in chunks:
        for span in chunk["spans"]:
            key = (span["block_id"], span["start"], span["end"])
            if key in seen:
                continue
            seen.add(key)
            result.append(
                await citation(
                    connection,
                    chunk,
                    {
                        "chunk_id": chunk["chunk_id"],
                        "block_id": span["block_id"],
                        "span_start": span["start"],
                        "span_end": span["end"],
                    },
                )
            )
    return merge_overlapping(result)


def merge_overlapping(sources):
    groups = {}
    for source in sources:
        key = (source["document_id"], source["parsing_revision"], source["block_id"])
        groups.setdefault(key, []).append(source)
    result = []
    for items in groups.values():
        merged = []
        for source in sorted(items, key=lambda s: (s["span_start"], s["span_end"])):
            current = dict(source)
            current["chunk_ids"] = [source["chunk_id"]]
            if merged and current["span_start"] <= merged[-1]["span_end"]:
                previous = merged[-1]
                if current["span_end"] > previous["span_end"]:
                    previous["quote"] += current["quote"][
                        previous["span_end"] - current["span_start"] :
                    ]
                    previous["span_end"] = current["span_end"]
                previous["chunk_ids"] = sorted(set(previous["chunk_ids"] + current["chunk_ids"]))
                previous["citation_id"] = str(
                    uuid5(
                        UUID(previous["block_id"]),
                        f"{previous['span_start']}:{previous['span_end']}",
                    )
                )
            else:
                merged.append(current)
        result.extend(merged)
    return result
