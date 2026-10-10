"""Administrative corpus import. No public document access is exposed here."""

import hashlib
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.registry.policy import validate_current_policy


def identity(value):
    return uuid5(NAMESPACE_URL, "pinui-registry:" + value)


def prepare_documents(manifest, workspace: Path, raw_root: Path):
    """Validate every original before import; keep a durable immutable volume copy."""
    validate_current_policy(manifest)
    prepared = []
    for row in manifest["documents"]:
        if row["download_status"] != "downloaded":
            continue
        source = (workspace / row["file"]).resolve()
        if not source.is_relative_to((workspace / "data/raw").resolve()):
            raise ValueError("Original is outside corpus storage")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            raise ValueError("Original checksum mismatch")
        key = "legislation/" + digest + source.suffix.lower()
        target = raw_root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as output, source.open("rb") as original:
                shutil.copyfileobj(original, output)
        except FileExistsError:
            pass
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("Stored original checksum mismatch")
        prepared.append((row, key))
    return prepared


def day(value):
    return date.fromisoformat(value) if value else None


def instant(value):
    return datetime.fromisoformat(value) if value else None


async def import_corpus(connection, manifest, sources, prepared):
    """Append only: repeat imports preserve IDs, manually reviewed statuses and audit."""
    source_map = {source["source_id"]: source for source in sources["sources"]}
    async with connection.transaction():
        # Serialize simultaneous imports, including migration-independent CLI runs.
        await connection.execute("SELECT pg_advisory_xact_lock(210021)")
        for source in source_map.values():
            await connection.execute(
                """INSERT INTO registry.source_registry VALUES ($1,'official',$2,$3,$4,now())
                ON CONFLICT(source_id) DO NOTHING""",
                source["source_id"],
                source["authority"],
                source.get("check_interval_seconds", 86400),
                json.dumps(source),
            )
        documents = {}
        for row, key in prepared:
            alias = row["download_id"]
            family = identity("family:" + alias)
            document = identity("document:" + alias + ":" + row["sha256"])
            source = source_map[row["source_id"]]
            await connection.execute(
                """INSERT INTO registry.document_families(family_id,slug,title)
                VALUES($1,$2,$3) ON CONFLICT DO NOTHING""",
                family,
                alias,
                row["title"],
            )
            result = await connection.execute(
                """INSERT INTO registry.document_versions
                (document_id,family_id,title,title_he,document_type,category,language,
                version_label,document_role,version_status,legal_status,verification_status,
                publication_date,effective_from,effective_to,source_id,source_url,source_name,
                issuer,raw_file_key,file_sha256,size_bytes,page_count,checked_at,metadata)
                VALUES($1,$2,$3,$3,'pdf',$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                $17,$18,$19,$20,$21,$22,$23) ON CONFLICT DO NOTHING""",
                document,
                family,
                row["title"],
                row["artifact_kind"],
                row["language"],
                row.get("version_label"),
                row["document_role"],
                row["version_status"],
                row["legal_status"],
                row["verification_status"],
                day(row.get("publication_date")),
                day(row.get("effective_from")),
                day(row.get("effective_to")),
                row["source_id"],
                row["url"],
                row.get("source_name", source["authority"]),
                row.get("issuer", source["authority"]),
                key,
                row["sha256"],
                row["size_bytes"],
                row["pdf_validation"]["pages"],
                instant(row.get("checked_at")),
                json.dumps(row),
            )
            documents[alias] = document
            if result == "INSERT 0 1":
                await connection.execute(
                    """INSERT INTO registry.audit_events VALUES
                    ($1,$2,'corpus_registered',$3,now())""",
                    identity("audit:" + str(document)),
                    document,
                    json.dumps({"origin": "corpus-manifest", "sha256": row["sha256"]}),
                )
            titles = row.get("family_titles_he", [])
            for position, topic in enumerate(row.get("families", [])):
                await connection.execute(
                    """INSERT INTO registry.document_topics VALUES ($1,$2,$3)
                    ON CONFLICT DO NOTHING""",
                    document,
                    topic,
                    titles[position] if position < len(titles) else topic,
                )
        for row in manifest["documents"]:
            snapshot = json.dumps(row, sort_keys=True, ensure_ascii=False)
            await connection.execute(
                """INSERT INTO registry.source_checks
                (check_id,download_id,source_id,document_id,source_url,download_status,
                checked_at,metadata) VALUES($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT DO NOTHING""",
                identity("check:" + snapshot),
                row["download_id"],
                row["source_id"],
                documents.get(row["download_id"]),
                row["url"],
                row["download_status"],
                instant(row.get("downloaded_at") or manifest["created_at"]),
                snapshot,
            )
        for gap in manifest.get("required_documents_not_acquired", []):
            snapshot = json.dumps(gap, sort_keys=True, ensure_ascii=False)
            await connection.execute(
                "INSERT INTO registry.coverage_gaps VALUES($1,$2,now()) ON CONFLICT DO NOTHING",
                identity("gap:" + snapshot),
                snapshot,
            )
