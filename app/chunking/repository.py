"""Administrative staging only. Corpus status is read from the registry, never activated."""

import json
from uuid import UUID

from app.chunking.core import verify_artifact
from app.registry.corpus import identity
from app.registry.legal_engine import canonical_hash


async def stage_artifact(connection, artifact, key, artifact_sha):
    document = artifact["document"]
    verify_artifact(artifact)
    revision = UUID(artifact["parsing_revision"])
    parsing_sha = canonical_hash(
        {
            k: artifact[k]
            for k in (
                "parsing_revision",
                "parser_fingerprint",
                "pages",
                "page_quality",
                "blocks",
                "paragraphs",
            )
            if k in artifact
        }
    )
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock(210023)")
        row = await connection.fetchrow(
            "SELECT * FROM registry.document_versions WHERE document_id=$1 FOR UPDATE",
            UUID(document["document_id"]),
        )
        if row is None or row["file_sha256"] != document["file_sha256"]:
            raise ValueError("Unregistered or changed original")
        if row["category"] == "consolidated_law":
            raise ValueError("Law chunks must originate from a verified legal snapshot")
        for key_name in (
            "version_status",
            "legal_status",
            "verification_status",
            "document_role",
            "source_id",
            "source_url",
            "category",
        ):
            if row[key_name] != document[key_name]:
                raise ValueError("Registry metadata changed; rebuild artifact")
        result = await connection.execute(
            """INSERT INTO registry.parsing_revisions
            (parsing_revision,document_id,parser_fingerprint,quality,manifest_key,artifact_sha256)
            VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING""",
            revision,
            row["document_id"],
            artifact["parser_fingerprint"],
            json.dumps(
                {
                    "pages": artifact["page_quality"],
                    "warnings": artifact["warnings"],
                    "status": "staged_unreviewed",
                    "first_artifact_sha256": artifact_sha,
                }
            ),
            key,
            parsing_sha,
        )
        existing = await connection.fetchval(
            "SELECT artifact_sha256 FROM registry.parsing_revisions WHERE parsing_revision=$1",
            revision,
        )
        if existing != parsing_sha:
            raise ValueError("Immutable artifact conflict")
        for block in artifact["blocks"]:
            await connection.execute(
                """INSERT INTO registry.blocks VALUES($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT DO NOTHING""",
                revision,
                UUID(block["block_id"]),
                block["ordinal"],
                block["original_text"],
                block["search_text"],
                json.dumps({"kind": block["normalization_map"]}),
                json.dumps(block["locator"]),
                json.dumps(
                    {
                        k: block[k]
                        for k in ("clause", "section", "group", "excluded", "structure_confidence")
                    }
                ),
            )
        for chunk in artifact["chunks"]:
            if chunk["current_norms_eligible"] or chunk["index_generation_id"] is not None:
                raise ValueError("Chunks must be staged without activation")
            await connection.execute(
                """INSERT INTO registry.chunks
                (chunk_id,parsing_revision,chunking_fingerprint,text,content_sha256,spans,metadata)
                VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT DO NOTHING""",
                UUID(chunk["chunk_id"]),
                revision,
                chunk["chunking_fingerprint"],
                chunk["text"],
                chunk["content_sha256"],
                json.dumps(chunk["spans"]),
                json.dumps({k: v for k, v in chunk.items() if k not in ("text", "spans")}),
            )
        counts = await connection.fetchrow(
            """SELECT (SELECT count(*) FROM registry.blocks WHERE parsing_revision=$1) AS blocks,
            (SELECT count(*) FROM registry.chunks WHERE parsing_revision=$1
             AND chunking_fingerprint=$2) AS chunks""",
            revision,
            artifact["chunking_fingerprint"],
        )
        if counts["blocks"] != len(artifact["blocks"]) or counts["chunks"] != len(
            artifact["chunks"]
        ):
            raise ValueError("Incomplete staging")
        if result == "INSERT 0 1":
            await connection.execute(
                """INSERT INTO registry.audit_events VALUES($1,$2,'chunks_staged',$3,now())""",
                identity("chunks-staged:" + str(revision)),
                row["document_id"],
                json.dumps(
                    {
                        "parsing_revision": str(revision),
                        "chunks": counts["chunks"],
                        "status": "staged_unreviewed",
                        "search_activated": False,
                    }
                ),
            )
    return dict(counts)
