"""Hybrid retrieval in a fixed PG access/generation scope; Qdrant is never authoritative."""

import asyncio
import json
import re
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import numpy as np
from qdrant_client import QdrantClient, models

from app.embeddings.onnx import LocalModel
from app.retrieval.expansion import expand_he
from app.retrieval.lexical import sparse
from app.services.access import documents
from app.services.errors import DomainError


class Retrieval:
    def __init__(self, settings):
        self.settings = settings
        self.manifest = json.loads(
            (settings.index_storage_path / "index-manifest.json").read_text()
        )
        configured = (
            settings.embedding_model,
            settings.embedding_revision,
            settings.embedding_dimension,
        )
        selected = self.manifest["model"]
        if configured != (selected["model"], selected["revision"], selected["dimension"]):
            raise ValueError("Configured embedding differs from active index")
        self.encoder = LocalModel(self.manifest["model"], settings.model_storage_path)
        self.reranker = LocalModel(
            self.manifest["reranker"], settings.model_storage_path, self.manifest["reranker_length"]
        )
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value() or None,
            timeout=30,
            check_compatibility=False,
        )
        self.lock = asyncio.Lock()

    async def scope(self, connection, actor, request):
        rows = await documents(connection, actor)
        explicit = set(request.document_ids)
        if explicit - {r["document_id"] for r in rows}:
            raise DomainError("NOT_FOUND", 404)
        mode = request.mode or (
            "project_documents" if explicit or request.project_id else "all_documents"
        )
        if mode == "project_documents" and not explicit and not request.project_id:
            raise DomainError("FILTER_CONFLICT", 422)
        if mode == "historical" and not request.as_of:
            raise DomainError("AS_OF_REQUIRED", 422)
        if mode == "historical":
            # Original editions alone do not establish applicability on a date.
            # Historical law requests use the separately reviewed chain compiler.
            raise DomainError("HISTORICAL_SNAPSHOT_UNCONFIRMED")
        if (
            request.as_of
            and mode != "historical"
            and request.as_of != datetime.now(ZoneInfo("Asia/Jerusalem")).date()
        ):
            raise DomainError("HISTORICAL_SNAPSHOT_REQUIRED")
        selected = []
        for row in rows:
            if explicit and row["document_id"] not in explicit:
                continue
            if request.project_id and row["project_id"] != request.project_id:
                if not (
                    request.include_shared_norms
                    and row["project_id"] is None
                    and row["current_norms_eligible"]
                ):
                    continue
            if request.category and row["category"] != request.category:
                continue
            if request.document_family_id and row["family_id"] != request.document_family_id:
                continue
            if row["legal_engine_required"]:
                if mode == "all_documents" and not explicit:
                    continue
                raise DomainError("LEGAL_CURRENTNESS_UNCONFIRMED")
            if mode == "current_norms" and not row["current_norms_eligible"]:
                continue
            if mode == "current_norms":
                interval = await connection.fetchval(
                    (
                        "SELECT check_interval_seconds FROM registry.source_regi"
                        "stry WHERE source_id=$1"
                    ),
                    row["source_id"],
                )
                if (
                    row["checked_at"] is None
                    or (datetime.now(UTC) - row["checked_at"]).total_seconds() > interval
                ):
                    raise DomainError("SOURCE_FRESHNESS_EXPIRED")
            if row["active_index_generation_id"] is None:
                if explicit:
                    raise DomainError("DOCUMENT_NOT_READY")
                continue
            generation = await connection.fetchrow(
                "SELECT * FROM registry.index_generations WHERE generation_id=$1",
                row["active_index_generation_id"],
            )
            if (
                generation["status"] != "active"
                or generation["collection_name"] != self.manifest["collection"]
            ):
                raise DomainError("INDEX_GENERATION_CHANGED")
            selected.append({"row": row, "generation": generation["generation_id"], "mode": mode})
        if explicit - {r["row"]["document_id"] for r in selected}:
            raise DomainError("FILTER_CONFLICT", 422)
        return selected

    async def revalidate(self, connection, actor, scope):
        accessible = {r["document_id"]: r for r in await documents(connection, actor)}
        for item in scope:
            row = accessible.get(item["row"]["document_id"])
            if row is None:
                raise DomainError("SOURCE_CHANGED")
            if row["active_index_generation_id"] != item["generation"]:
                raise DomainError("SOURCE_CHANGED")
            for key in (
                "file_sha256",
                "verification_status",
                "version_status",
                "legal_status",
                "category",
                "document_role",
                "source_url",
                "issuer",
                "legal_engine_required",
            ):
                if row[key] != item["row"][key]:
                    raise DomainError("SOURCE_CHANGED")
            if item["mode"] == "current_norms" and not row["current_norms_eligible"]:
                raise DomainError("LEGAL_CURRENTNESS_UNCONFIRMED")
            if item["mode"] == "current_norms":
                interval = await connection.fetchval(
                    "SELECT check_interval_seconds FROM registry.source_registry "
                    "WHERE source_id=$1",
                    row["source_id"],
                )
                if (
                    row["checked_at"] is None
                    or (datetime.now(UTC) - row["checked_at"]).total_seconds() > interval
                ):
                    raise DomainError("SOURCE_FRESHNESS_EXPIRED")

    async def search(self, connection, actor, scope, query):
        if not scope:
            return []
        generations = [str(item["generation"]) for item in scope]
        filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="index_generation_id", match=models.MatchAny(any=generations)
                )
            ]
        )
        async with self.lock:
            variants = (
                expand_he(query, self.settings.max_query_variants)
                if self.settings.use_query_expansion
                else [query]
            )
            if (
                self.encoder.count(self.encoder.spec["query_prefix"] + query)
                > self.encoder.max_length
            ):
                raise DomainError("QUERY_TOO_LONG", 422)
            variants = [
                v
                for v in variants
                if self.encoder.count(self.encoder.spec["query_prefix"] + v)
                <= self.encoder.max_length
            ]
            vectors = await asyncio.to_thread(self.encoder.encode, variants, True)
            prefetch = []
            for variant, dense in zip(variants, vectors, strict=True):
                lexical = sparse(
                    variant,
                    self.manifest["vocabulary"],
                    self.manifest["average_length"],
                    query=True,
                )
                prefetch.append(
                    models.Prefetch(
                        query=dense.tolist(),
                        using="dense",
                        filter=filter,
                        limit=self.settings.dense_top_k,
                    )
                )
                if lexical["indices"]:
                    prefetch.append(
                        models.Prefetch(
                            query=models.SparseVector(**lexical),
                            using="lexical",
                            filter=filter,
                            limit=self.settings.sparse_top_k,
                        )
                    )
            result = await asyncio.to_thread(
                self.client.query_points,
                self.manifest["collection"],
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=filter,
                limit=self.settings.retrieval_top_k,
                with_payload=True,
            )
            candidates = []
            authority = {str(i["row"]["document_id"]): i["row"] for i in scope}
            for point in result.points:
                row = await connection.fetchrow(
                    "SELECT * FROM registry.chunks WHERE chunk_id=$1",
                    UUID(point.payload["chunk_id"]),
                )
                if row is None:
                    raise DomainError("INDEX_EVIDENCE_MISMATCH")
                metadata = json.loads(row["metadata"])
                if point.payload["content_sha256"] != row["content_sha256"]:
                    raise DomainError("INDEX_EVIDENCE_MISMATCH")
                if metadata["document_id"] not in {str(i["row"]["document_id"]) for i in scope}:
                    raise DomainError("INDEX_SCOPE_MISMATCH")
                linked = await connection.fetchval(
                    (
                        "SELECT EXISTS(SELECT 1 FROM registry.generation_chunks "
                        "WHERE generation_id=$1 AND chunk_id=$2 AND point_id=$3)"
                    ),
                    UUID(point.payload["index_generation_id"]),
                    row["chunk_id"],
                    UUID(str(point.id)),
                )
                if not linked:
                    raise DomainError("INDEX_SCOPE_MISMATCH")
                candidates.append(
                    {
                        "text": row["text"],
                        "spans": json.loads(row["spans"]),
                        **metadata,
                        **{
                            key: authority[metadata["document_id"]][key]
                            for key in (
                                "category",
                                "document_role",
                                "version_status",
                                "legal_status",
                                "verification_status",
                                "source_url",
                                "version_label",
                            )
                        },
                    }
                )
            clause = re.search(r"(?:סעיף|clause|пункт)\s+(\d+(?:\.\d+)*)", query, re.I)
            if clause:
                exact = await connection.fetch(
                    """SELECT c.* FROM registry.chunks c
                    JOIN registry.generation_chunks g USING(chunk_id)
                    WHERE g.generation_id=ANY($1::uuid[]) AND c.metadata->>'clause'=$2
                    ORDER BY c.chunk_id LIMIT 30""",
                    [UUID(g) for g in generations],
                    clause.group(1),
                )
                seen = {c["chunk_id"] for c in candidates}
                for row in exact:
                    if str(row["chunk_id"]) not in seen:
                        candidates.append(
                            {
                                "text": row["text"],
                                "spans": json.loads(row["spans"]),
                                **json.loads(row["metadata"]),
                            }
                        )
            if not candidates:
                return []
            for candidate in candidates:
                candidate.update(
                    {
                        key: authority[candidate["document_id"]][key]
                        for key in (
                            "category",
                            "document_role",
                            "verification_status",
                            "version_status",
                            "legal_status",
                            "version_label",
                            "source_url",
                        )
                    }
                )
            scores = await asyncio.to_thread(
                self.reranker.rank, query, [c["text"] for c in candidates]
            )
            ordered = [
                {**candidates[i], "rerank_score": float(scores[i])}
                for i in np.argsort(-scores)[: self.settings.rerank_top_k]
            ]
        await self.revalidate(connection, actor, scope)
        return [c for c in ordered if c["rerank_score"] >= self.settings.rerank_min_score]
