"""Safe rechecks retain provenance, never auto-approve new legal text."""

import asyncio
import hashlib
import json
from uuid import uuid4

from scripts.download_corpus import fetch_pdf


async def check_source(connection, settings, source_id):
    rows = await connection.fetch(
        "SELECT * FROM registry.document_versions WHERE source_id=$1", source_id
    )
    counters = {"unchanged": 0, "changed": 0, "failed": 0}
    for row in rows:
        status, details = "failed", {}
        try:
            data, url, etag, modified = await asyncio.to_thread(fetch_pdf, row["source_url"])
            sha = hashlib.sha256(data).hexdigest()
            details = {"sha256": sha, "final_url": url, "etag": etag, "last_modified": modified}
            status = "downloaded"
            if sha == row["file_sha256"]:
                counters["unchanged"] += 1
                # An unchanged PDF proves content stability, not that a newer law does not exist.
                details["currentness_review_renewed"] = False
            else:
                counters["changed"] += 1
                target = settings.raw_storage_path / "pending-source-changes" / (sha + ".pdf")
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_bytes(data)
                details["pending_file"] = str(target.relative_to(settings.raw_storage_path))
                await connection.execute(
                    (
                        "UPDATE registry.document_versions SET verification_stat"
                        "us='manual_review' WHERE document_id=$1"
                    ),
                    row["document_id"],
                )
        except Exception:
            counters["failed"] += 1
            details = {"error_code": "SOURCE_CHECK_FAILED"}
        await connection.execute(
            (
                "INSERT INTO registry.source_checks\n            (check_i"
                "d,download_id,source_id,document_id,source_url,download"
                "_status,checked_at,metadata)\n            VALUES($1,$2,$"
                "3,$4,$5,$6,now(),$7)"
            ),
            uuid4(),
            str(row["document_id"]),
            source_id,
            row["document_id"],
            row["source_url"],
            status,
            json.dumps(details),
        )
    return counters
