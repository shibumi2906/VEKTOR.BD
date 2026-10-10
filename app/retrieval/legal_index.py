"""Vector adapter accepts only compiler-verified immutable legal snapshots."""

from uuid import UUID, uuid5

import numpy as np
from qdrant_client import models

from app.chunking.core import create_chunks, verify_chunks
from app.registry.corpus import identity
from app.registry.legal_engine import canonical_hash
from app.retrieval.legal_scope import revalidate_legal_scope, validate_legal_hit
from app.retrieval.lexical import sparse, tokens


def snapshot_chunks(scope, model):
    chunks = []
    for snapshot in scope.snapshots:
        if snapshot.status != "verified":
            raise ValueError("Only verified snapshots may be indexed")
        document = str(identity("law:" + snapshot.law_slug))
        revision = str(uuid5(UUID(document), snapshot.snapshot_sha256))
        blocks = []
        for i, clause in enumerate(snapshot.clauses):
            block = str(uuid5(UUID(revision), clause.clause_id))
            blocks.append(
                {
                    "block_id": block,
                    "ordinal": i,
                    "original_text": clause.text_he,
                    "search_text": clause.text_he,
                    "normalization_map": "identity-v1",
                    "locator": {
                        "legal_clause_id": clause.clause_id,
                        "is_derived_text": True,
                        "displayed_page": None,
                        "paragraph_id": None,
                    },
                    "clause": clause.clause_id,
                    "section": clause.clause_id.split(".")[0],
                    "group": i,
                    "excluded": False,
                    "structure_confidence": "high",
                }
            )
        metadata = {
            "document_id": document,
            "document_alias": snapshot.law_slug,
            "document_type": "legal_snapshot",
            "category": "consolidated_law",
            "legal_snapshot_sha256": snapshot.snapshot_sha256,
            "as_of": snapshot.as_of.isoformat(),
        }
        config = {
            "tokenizer": model["model"] + "@" + model["revision"],
            "tokenizer_model_name": model["name"],
            "max_tokens": model["max_length"] - 32,
            "overlap_tokens": 16,
        }
        _, values = create_chunks(metadata, revision, blocks, config)
        verify_chunks(blocks, values, config["max_tokens"])
        chunks.extend(values)
    return chunks


def retrieve(engine, scope, query):
    chunks = snapshot_chunks(scope, engine.manifest["model"])
    fingerprint = canonical_hash(
        {
            "model": engine.manifest["model"],
            "snapshots": [s.snapshot_sha256 for s in scope.snapshots],
        }
    )
    collection = "pinui_legal_" + fingerprint[:24]
    vocabulary = {
        t: i for i, t in enumerate(sorted({t for c in chunks for t in tokens(c["text"])}))
    }
    average = sum(len(tokens(c["text"])) for c in chunks) / len(chunks)
    points = {str(uuid5(UUID(c["chunk_id"]), fingerprint)): c for c in chunks}
    if not engine.client.collection_exists(collection):
        engine.client.create_collection(
            collection,
            vectors_config={
                "dense": models.VectorParams(
                    size=engine.manifest["model"]["dimension"], distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                "lexical": models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
    # Verify exact immutable point identities, repair a crash during staged upload.
    stored, offset = [], None
    while True:
        batch, offset = engine.client.scroll(
            collection, limit=256, offset=offset, with_payload=True
        )
        stored.extend(batch)
        if offset is None:
            break
    if {str(p.id) for p in stored} != set(points):
        vectors = engine.encoder.encode([c["text"] for c in chunks])
        values = [
            models.PointStruct(
                id=point,
                payload={
                    "chunk_id": chunk["chunk_id"],
                    "snapshot": chunk["legal_snapshot_sha256"],
                    "sha256": chunk["content_sha256"],
                },
                vector={
                    "dense": vectors[i].tolist(),
                    "lexical": models.SparseVector(**sparse(chunk["text"], vocabulary, average)),
                },
            )
            for i, (point, chunk) in enumerate(points.items())
        ]
        for index in range(0, len(values), 64):
            engine.client.upsert(collection, values[index : index + 64], wait=True)
        if engine.client.count(collection, exact=True).count != len(chunks):
            raise ValueError("Legal generation is incomplete")
    vector = engine.encoder.encode([query], query=True)[0]
    lexical = sparse(query, vocabulary, average, query=True)
    prefetch = [models.Prefetch(query=vector.tolist(), using="dense", limit=30)]
    if lexical["indices"]:
        prefetch.append(
            models.Prefetch(query=models.SparseVector(**lexical), using="lexical", limit=30)
        )
    hits = engine.client.query_points(
        collection,
        prefetch=prefetch,
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=30,
        with_payload=True,
    ).points
    candidates = []
    for hit in hits:
        chunk = points.get(str(hit.id))
        if chunk is None or hit.payload != {
            "chunk_id": chunk["chunk_id"],
            "snapshot": chunk["legal_snapshot_sha256"],
            "sha256": chunk["content_sha256"],
        }:
            raise ValueError("Legal index evidence mismatch")
        candidates.append(chunk)
    if not candidates:
        return []
    scores = engine.reranker.rank(query, [c["text"] for c in candidates])
    return [
        {**candidates[i], "rerank_score": float(scores[i])}
        for i in np.argsort(-scores)[:7]
        if scores[i] >= engine.settings.rerank_min_score
    ]


async def search_legal(connection, engine, scope, query):
    import asyncio

    async with engine.lock:
        chunks = await asyncio.to_thread(retrieve, engine, scope, query)
    for chunk in chunks:
        for span in chunk["spans"]:
            validate_legal_hit(
                scope,
                law_slug=chunk["document_alias"],
                clause_id=chunk["clause"],
                snapshot_sha256=chunk["legal_snapshot_sha256"],
                start=span["start"],
                end=span["end"],
                text_he=chunk["text"][span["chunk_start"] : span["chunk_end"]],
            )
    await revalidate_legal_scope(connection, scope)
    return chunks
