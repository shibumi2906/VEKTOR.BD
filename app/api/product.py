import asyncio
import copy
import hashlib
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse

from app.models.query import CompareRequest, QueryRequest
from app.models.responses import CompareResponse, QueryResponse
from app.registry.aliases import resolve
from app.services.access import authenticate, document, documents, local_owner
from app.services.comparison import compare
from app.services.database import connect
from app.services.errors import DomainError
from app.services.query import execute

router = APIRouter()


async def session(request: Request):
    settings = request.app.state.settings
    header = request.headers.get("Authorization", "")
    if settings.auth_mode == "token" and (not header.startswith("Bearer ") or not header[7:]):
        raise DomainError("UNAUTHORIZED", 401)
    connection = await connect(settings)
    try:
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        actor = (
            await local_owner(connection)
            if settings.auth_mode == "local"
            else await authenticate(connection, settings, token)
        )
        yield connection, actor
    finally:
        await connection.close()


def retrieval(request):
    result = getattr(request.app.state, "retrieval", None)
    if result is None:
        raise DomainError("LOCAL_INDEX_UNAVAILABLE", 503)
    # A completed job can switch the active collection. Each request freezes its manifest.
    scoped = copy.copy(result)
    try:
        scoped.manifest = json.loads(
            (request.app.state.settings.index_storage_path / "index-manifest.json").read_text()
        )
    except (OSError, ValueError) as exc:
        raise DomainError("LOCAL_INDEX_UNAVAILABLE", 503) from exc
    if scoped.manifest["model"] != result.manifest["model"]:
        raise DomainError("MODEL_RESTART_REQUIRED", 503)
    return scoped


@router.get("/documents/resolve")
async def resolve_document(
    reference: str, context: Annotated[tuple, Depends(session)], project_id: UUID | None = None
):
    connection, actor = context
    matches = resolve(await documents(connection, actor), reference, project_id)
    if not matches:
        raise DomainError("NOT_FOUND", 404)
    return {
        "status": "resolved" if len(matches) == 1 else "clarification_required",
        "candidates": [
            {k: r[k] for k in ("document_id", "title", "version_label", "project_id")}
            for r in matches
        ],
    }


@router.get("/documents")
async def list_documents(
    request: Request,
    context: Annotated[tuple, Depends(session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cursor: UUID | None = None,
    project_id: UUID | None = None,
    category: str | None = None,
    document_family_id: UUID | None = None,
):
    connection, actor = context
    rows = await documents(connection, actor)
    rows = sorted(
        (
            r
            for r in rows
            if (cursor is None or r["document_id"].int > cursor.int)
            and (project_id is None or r["project_id"] == project_id)
            and (category is None or r["category"] == category)
            and (document_family_id is None or r["family_id"] == document_family_id)
        ),
        key=lambda r: r["document_id"].int,
    )
    page = rows[:limit]
    fields = (
        "document_id",
        "family_id",
        "title",
        "title_he",
        "document_alias",
        "project_id",
        "document_type",
        "category",
        "document_role",
        "version_label",
        "version_status",
        "verification_status",
        "legal_status",
        "ingestion_status",
        "source_url",
        "issuer",
        "publication_date",
        "page_count",
        "current_norms_eligible",
    )
    return {
        "documents": [{k: row[k] for k in fields} for row in page],
        "next_cursor": str(page[-1]["document_id"]) if len(rows) > limit else None,
    }


@router.get("/documents/{document_id}/source")
@router.get("/documents/{document_id}/original")
async def original(
    document_id: UUID, request: Request, context: Annotated[tuple, Depends(session)]
):
    connection, actor = context
    row = await document(connection, actor, document_id)
    root = request.app.state.settings.raw_storage_path.resolve()
    path = (root / row["raw_file_key"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise DomainError("ORIGINAL_UNAVAILABLE", 404)
    sha = await asyncio.to_thread(lambda: hashlib.sha256(path.read_bytes()).hexdigest())
    if sha != row["file_sha256"]:
        raise DomainError("ORIGINAL_CHECKSUM_MISMATCH")
    return FileResponse(
        path,
        filename=str(document_id) + path.suffix,
        media_type="application/pdf"
        if path.suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest, request: Request, context: Annotated[tuple, Depends(session)]):
    connection, actor = context
    return await asyncio.wait_for(
        execute(
            connection,
            actor,
            retrieval(request),
            request.app.state.settings,
            body,
            UUID(request.state.request_id),
        ),
        timeout=request.app.state.settings.query_timeout_seconds,
    )


@router.post("/compare", response_model=CompareResponse)
async def comparison(
    body: CompareRequest, request: Request, context: Annotated[tuple, Depends(session)]
):
    connection, actor = context
    return await asyncio.wait_for(
        compare(
            connection,
            actor,
            retrieval(request),
            request.app.state.settings,
            body,
            UUID(request.state.request_id),
        ),
        timeout=request.app.state.settings.query_timeout_seconds,
    )


@router.get("/documents/{document_id}")
async def details(document_id: UUID, context: Annotated[tuple, Depends(session)]):
    connection, actor = context
    row = await document(connection, actor, document_id)
    return {
        k: row[k]
        for k in (
            "document_id",
            "title",
            "document_alias",
            "version_label",
            "document_role",
            "verification_status",
            "legal_status",
            "ingestion_status",
            "page_count",
            "document_type",
            "source_url",
            "issuer",
            "project_id",
            "file_sha256",
            "size_bytes",
            "family_id",
            "version_status",
            "effective_from",
            "effective_to",
            "checked_at",
            "source_name",
        )
    }
