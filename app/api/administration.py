import hashlib
import json
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import ValidationError

from app.api.product import session
from app.jobs.queue import enqueue
from app.models.administration import Grant, IndexRequest, ProjectCreate, UploadMetadata
from app.models.review import DocumentReview
from app.registry.corpus import identity
from app.services.access import document, require_admin
from app.services.errors import DomainError

router = APIRouter()
Context = Annotated[tuple, Depends(session)]


@router.post("/documents/{document_id}/review")
async def review_document(document_id: UUID, body: DocumentReview, context: Context):
    from datetime import datetime
    from urllib.parse import urlsplit
    from zoneinfo import ZoneInfo

    connection, actor = context
    require_admin(actor)
    row = await document(connection, actor, document_id)
    if row["category"] == "consolidated_law":
        raise DomainError("LEGAL_CHAIN_REVIEW_REQUIRED")
    if body.file_sha256 != row["file_sha256"]:
        raise DomainError("SOURCE_CHANGED")
    today = datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    if body.reviewed_through != today:
        raise DomainError("REVIEW_DATE_REQUIRED", 422)
    source = await connection.fetchval(
        "SELECT metadata FROM registry.source_registry WHERE source_id=$1", row["source_id"]
    )
    allowed = json.loads(source)
    url = urlsplit(str(body.inventory_source_url))
    if row["document_role"] == "official" and (
        url.scheme != "https"
        or url.hostname not in allowed.get("allowed_hosts", [])
        or not any(
            url.path.startswith(prefix) for prefix in allowed.get("allowed_path_prefixes", [])
        )
    ):
        raise DomainError("UNTRUSTED_REVIEW_SOURCE", 422)
    if row["document_role"] != "official" and body.legal_status != "not_applicable":
        raise DomainError("SOURCE_TYPE_CONFLICT", 422)
    if body.effective_to and body.effective_from and body.effective_to <= body.effective_from:
        raise DomainError("INVALID_EFFECTIVE_INTERVAL", 422)
    async with connection.transaction():
        await connection.execute(
            """UPDATE registry.document_versions SET version_status=$2,
            legal_status=$3,verification_status=$4,effective_from=$5,effective_to=$6,
            checked_at=now() WHERE document_id=$1""",
            document_id,
            body.version_status,
            body.legal_status,
            body.verification_status,
            body.effective_from,
            body.effective_to,
        )
        if body.version_status == "current":
            await connection.execute(
                "UPDATE registry.document_versions SET version_status='superseded' "
                "WHERE family_id=$1 AND document_id<>$2 AND version_status='current'",
                row["family_id"],
                document_id,
            )
            await connection.execute(
                "UPDATE registry.document_families SET current_document_id=$2 WHERE family_id=$1",
                row["family_id"],
                document_id,
            )
        await connection.execute(
            "INSERT INTO registry.audit_events VALUES($1,$2,'document_review',$3,now())",
            uuid4(),
            document_id,
            json.dumps(
                {"actor_id": str(actor["actor_id"]), "review": body.model_dump(mode="json")}
            ),
        )
    return {"document_id": str(document_id), "verification_status": body.verification_status}


@router.get("/projects")
async def projects(context: Context):
    connection, actor = context
    rows = await connection.fetch(
        """SELECT p.* FROM registry.projects p WHERE $1='admin' OR EXISTS
        (SELECT 1 FROM registry.project_grants g WHERE g.project_id=p.project_id AND g.actor_id=$2)
        ORDER BY p.created_at""",
        actor["role"],
        actor["actor_id"],
    )
    return {"projects": [dict(r) for r in rows]}


@router.post("/projects", status_code=201)
async def create_project(body: ProjectCreate, context: Context):
    connection, actor = context
    require_admin(actor)
    identifier = identity("project:" + body.slug)
    await connection.execute(
        "INSERT INTO registry.projects VALUES($1,$2,$3,now()) ON CONFLICT DO NOTHING",
        identifier,
        body.slug,
        body.title,
    )
    return {"project_id": str(identifier)}


@router.post("/projects/{project_id}/grants")
async def grant(project_id: UUID, body: Grant, request: Request, context: Context):
    connection, actor = context
    require_admin(actor)
    if not await connection.fetchval(
        "SELECT EXISTS(SELECT 1 FROM registry.projects WHERE project_id=$1)", project_id
    ):
        raise DomainError("NOT_FOUND", 404)
    reader = identity("actor:reader")
    secret = request.app.state.settings.reader_api_token.get_secret_value()
    if not secret:
        raise DomainError("READER_NOT_CONFIGURED")
    await connection.execute(
        "INSERT INTO registry.actors VALUES($1,'reader',$2,true) ON CONFLICT DO NOTHING",
        reader,
        hashlib.sha256(secret.encode()).hexdigest(),
    )
    async with connection.transaction():
        if body.enabled:
            await connection.execute(
                "INSERT INTO registry.project_grants VALUES($1,$2) ON CONFLICT DO NOTHING",
                reader,
                project_id,
            )
        else:
            await connection.execute(
                "DELETE FROM registry.project_grants WHERE actor_id=$1 AND project_id=$2",
                reader,
                project_id,
            )
        await connection.execute(
            "INSERT INTO registry.audit_events VALUES($1,NULL,'project_grant',$2,now())",
            uuid4(),
            json.dumps(
                {
                    "actor_id": str(actor["actor_id"]),
                    "project_id": str(project_id),
                    "reader_enabled": body.enabled,
                }
            ),
        )
    return {"project_id": str(project_id), "reader_enabled": body.enabled}


@router.post("/documents", status_code=202)
async def upload(
    request: Request,
    context: Context,
    metadata: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    connection, actor = context
    require_admin(actor)
    try:
        body = UploadMetadata.model_validate_json(metadata)
    except ValidationError as exc:
        raise DomainError("INVALID_METADATA", 422) from exc
    if not await connection.fetchval(
        "SELECT EXISTS(SELECT 1 FROM registry.projects WHERE project_id=$1)", body.project_id
    ):
        raise DomainError("NOT_FOUND", 404)
    settings = request.app.state.settings
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise DomainError("UPLOAD_TOO_LARGE", 413)
    suffix = (
        ".pdf" if data.startswith(b"%PDF-") else ".docx" if data.startswith(b"PK\x03\x04") else None
    )
    if not suffix:
        raise DomainError("UNSUPPORTED_FILE_TYPE", 415)
    if suffix == ".docx":
        import io
        import zipfile

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("Missing OOXML body")
        except (ValueError, zipfile.BadZipFile) as exc:
            raise DomainError("INVALID_DOCUMENT", 415) from exc
    sha = hashlib.sha256(data).hexdigest()
    family = identity(f"upload-family:{body.project_id}:{body.family_slug}")
    identifier = identity(f"upload-document:{family}:{sha}")
    key = "uploads/" + sha + suffix
    target = settings.raw_storage_path / key
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        try:
            with target.open("xb") as output:
                output.write(data)
        except FileExistsError:
            pass
    if hashlib.sha256(target.read_bytes()).hexdigest() != sha:
        raise DomainError("ORIGINAL_CHECKSUM_MISMATCH")
    async with connection.transaction():
        await connection.execute(
            "INSERT INTO registry.source_registry VALUES('private-up"
            "load','manual','Загрузка',86400,'{}',now()) ON CONFLICT"
            " DO NOTHING"
        )
        await connection.execute(
            (
                "INSERT INTO registry.document_families(family_id,slug,t"
                "itle,project_id) VALUES($1,$2,$3,$4) ON CONFLICT DO NOT"
                "HING"
            ),
            family,
            body.family_slug,
            body.title,
            body.project_id,
        )
        await connection.execute(
            """INSERT INTO registry.document_versions
            (document_id,family_id,title,title_he,document_type,category,language,version_label,
            document_role,version_status,legal_status,verification_status,source_id,source_url,
            source_name,issuer,raw_file_key,file_sha256,size_bytes,page_count,metadata)
            VALUES($1,$2,$3,$3,$4,$5,'he',$6,$7,'unknown','not_applicable','manual_review',
            'private-upload','','Загруженный файл','Не подтверждён',$8,$9,$10,NULL,$11)
            ON CONFLICT DO NOTHING""",
            identifier,
            family,
            body.title,
            suffix[1:],
            body.category,
            body.version_label,
            body.document_role,
            key,
            sha,
            len(data),
            body.model_dump_json(),
        )
        payload = {
            "document_id": str(identifier),
            "metadata": body.model_dump(mode="json"),
            "sha256": sha,
        }
        return await enqueue(
            connection,
            actor,
            "/documents",
            request.headers.get("Idempotency-Key"),
            "ingest",
            payload,
            identifier,
        )


@router.post("/documents/index", status_code=202)
async def index(body: IndexRequest, request: Request, context: Context):
    connection, actor = context
    require_admin(actor)
    await document(connection, actor, body.document_id)
    return await enqueue(
        connection,
        actor,
        "/documents/index",
        request.headers.get("Idempotency-Key"),
        "index",
        body.model_dump(mode="json"),
        body.document_id,
    )


@router.post("/documents/{document_id}/reindex", status_code=202)
async def reindex(document_id: UUID, request: Request, context: Context):
    connection, actor = context
    require_admin(actor)
    await document(connection, actor, document_id)
    return await enqueue(
        connection,
        actor,
        "/documents/reindex",
        request.headers.get("Idempotency-Key"),
        "reindex",
        {"document_id": str(document_id)},
        document_id,
    )


async def job_access(connection, actor, job_id):
    row = await connection.fetchrow("SELECT * FROM registry.jobs WHERE job_id=$1", job_id)
    if row is None:
        raise DomainError("NOT_FOUND", 404)
    if actor["role"] != "admin":
        if row["actor_id"] != actor["actor_id"]:
            raise DomainError("NOT_FOUND", 404)
        if row["document_id"]:
            await document(connection, actor, row["document_id"])
    return row


@router.get("/jobs/{job_id}")
async def job(job_id: UUID, context: Context):
    connection, actor = context
    row = await job_access(connection, actor, job_id)
    return {
        k: json.loads(row[k]) if k == "result" and row[k] else row[k]
        for k in (
            "job_id",
            "type",
            "status",
            "stage",
            "progress",
            "attempt",
            "error_code",
            "result",
        )
    }


@router.post("/jobs/{job_id}/cancel", status_code=202)
async def cancel(job_id: UUID, context: Context):
    connection, actor = context
    await job_access(connection, actor, job_id)
    await connection.execute(
        (
            "UPDATE registry.jobs SET cancel_requested=true WHERE jo"
            "b_id=$1 AND status IN ('pending','running')"
        ),
        job_id,
    )
    return {"job_id": str(job_id), "cancel_requested": True}


@router.get("/sources")
async def sources(context: Context):
    connection, actor = context
    require_admin(actor)
    return {
        "sources": [
            dict(r)
            for r in await connection.fetch(
                "SELECT source_id,source_type,source_name,check_interval"
                "_seconds FROM registry.source_registry ORDER BY source_"
                "id"
            )
        ]
    }


@router.post("/sources/{source_id}/check", status_code=202)
async def check(source_id: str, request: Request, context: Context):
    connection, actor = context
    require_admin(actor)
    if not await connection.fetchval(
        (
            "SELECT EXISTS(SELECT 1 FROM registry.source_registry WH"
            "ERE source_id=$1 AND source_type='official')"
        ),
        source_id,
    ):
        raise DomainError("NOT_FOUND", 404)
    return await enqueue(
        connection,
        actor,
        "/sources/check",
        request.headers.get("Idempotency-Key"),
        "source_check",
        {"source_id": source_id},
    )
