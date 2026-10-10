"""Explicit administrator cleanup authorized by the user, never automatic reindexing.

Plan uses an exact manifest hash and checksums; unknown files and private contracts are untouched.
Interrupted filesystem cleanup can be resumed with the same plan.
"""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg

from app.config.settings import Settings
from app.registry.corpus import identity


def checked_target(path, root, digest):
    path = path.resolve()
    root = root.resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Cleanup target is outside the authorized corpus directory")
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("Cleanup checksum changed; no deletion performed")
    return path


async def apply_plan(workspace, plan):
    manifest_path = workspace / "data/corpus-manifest.json"
    existing = manifest_path.read_bytes()
    expected = plan["manifest_sha256"]
    if hashlib.sha256(existing).hexdigest() != expected:
        raise ValueError("Manifest changed after cleanup planning")
    manifest = json.loads(existing)
    removed = {r["download_id"]: r for r in plan["remove"]}
    retained = [r for r in manifest["documents"] if r["download_id"] not in removed]
    retained_hashes = {r.get("sha256") for r in retained}
    targets = []
    settings = Settings()
    for row in removed.values():
        if row.get("file"):
            targets.append(
                checked_target(workspace / row["file"], workspace / "data/raw", row["sha256"])
            )
            if row["sha256"] not in retained_hashes:
                targets.append(
                    checked_target(
                        settings.raw_storage_path / ("legislation/" + row["sha256"] + ".pdf"),
                        settings.raw_storage_path / "legislation",
                        row["sha256"],
                    )
                )
    # Earlier acquisition stages may have made additional copies under other names.
    retired_hashes = {r.get("sha256") for r in removed.values()} - retained_hashes - {None}
    for root in (workspace / "data/raw/legislation", settings.raw_storage_path / "legislation"):
        for copy in root.glob("*.pdf"):
            digest = hashlib.sha256(copy.read_bytes()).hexdigest()
            if digest in retired_hashes:
                targets.append(checked_target(copy, root, digest))
    connection = await asyncpg.connect(
        settings.postgres_url.get_secret_value().replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )
    )
    try:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(210021)")
            for alias, row in removed.items():
                versions = await connection.fetch(
                    """SELECT d.document_id,d.file_sha256,d.ingestion_status
                    FROM registry.document_versions d JOIN registry.document_families f
                    USING(family_id) WHERE f.slug=$1 FOR UPDATE OF d""",
                    alias,
                )
                for version in versions:
                    if (
                        version["file_sha256"] != row.get("sha256")
                        or version["ingestion_status"] != "registered"
                    ):
                        raise ValueError("Registry differs from plan or has indexed data")
                    document = version["document_id"]
                    await connection.execute(
                        """UPDATE registry.document_families SET current_document_id=null
                        WHERE current_document_id=$1""",
                        document,
                    )
                    await connection.execute(
                        "DELETE FROM registry.document_topics WHERE document_id=$1", document
                    )
                    # Keep the registration audit but remove document content from history.
                    await connection.execute(
                        "UPDATE registry.audit_events SET document_id=null WHERE document_id=$1",
                        document,
                    )
                    await connection.execute(
                        "DELETE FROM registry.source_checks WHERE document_id=$1", document
                    )
                    await connection.execute(
                        "DELETE FROM registry.document_versions WHERE document_id=$1", document
                    )
                await connection.execute(
                    "DELETE FROM registry.source_checks WHERE download_id=$1", alias
                )
                await connection.execute(
                    "DELETE FROM registry.document_families WHERE slug=$1", alias
                )
            for gap in plan["gaps"]:
                snapshot = json.dumps(gap, sort_keys=True, ensure_ascii=False)
                await connection.execute(
                    "INSERT INTO registry.coverage_gaps VALUES($1,$2,now()) ON CONFLICT DO NOTHING",
                    identity("gap:" + snapshot),
                    snapshot,
                )
            await connection.execute(
                "INSERT INTO registry.audit_events VALUES($1,null,'user_corpus_cleanup',$2,now())",
                uuid4(),
                json.dumps(
                    {
                        "plan_sha256": hashlib.sha256(
                            json.dumps(plan, sort_keys=True).encode()
                        ).hexdigest(),
                        "removed_documents": sum(bool(r.get("file")) for r in removed.values()),
                        "reason": "User requested one current document, no amendment originals",
                    }
                ),
            )
        # Delete only individually verified paths. No recursive deletion or archive copies.
        for target in set(targets):
            target.unlink(missing_ok=True)
        config_path = workspace / "config/corpus-downloads.json"
        config = json.loads(config_path.read_text("utf-8"))
        config["documents"] = [r for r in config["documents"] if r["download_id"] not in removed]
        config["retention_policy"] = "current_only"
        config["required_documents_not_acquired"] = plan["gaps"]
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", "utf-8")
        manifest["documents"] = retained
        manifest["retention_policy"] = "current_only"
        manifest["legal_verification_complete"] = False
        manifest["required_documents_not_acquired"] = plan["gaps"]
        manifest["cleanup"] = {
            "removed_pdf_records": sum(bool(r.get("file")) for r in removed.values()),
            "replacement_complete": False,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(
            json.dumps(
                {
                    "remaining_documents": len(retained),
                    "removed_pdf_records": manifest["cleanup"]["removed_pdf_records"],
                    "gaps": len(plan["gaps"]),
                }
            )
        )
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        asyncio.run(apply_plan(args.workspace, json.loads(args.plan.read_text("utf-8"))))
    except Exception:
        print("Corpus cleanup failed; check plan, registry and original integrity.")
        sys.exit(1)


if __name__ == "__main__":
    main()
