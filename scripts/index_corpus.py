"""Idempotent staged indexing: immutable chunks, verified Qdrant points, atomic PG activation."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid5

import numpy as np
from qdrant_client import QdrantClient, models

from app.chunking.core import create_chunks, verify_artifact
from app.chunking.repository import stage_artifact
from app.config.settings import Settings
from app.embeddings.cache import load_cache, save_cache
from app.embeddings.onnx import LocalModel
from app.registry.corpus import identity
from app.registry.legal_engine import canonical_hash
from app.retrieval.lexical import sparse, tokens
from app.services.database import connect


async def run():
    settings = Settings()
    config = json.loads(Path("config/local-models.json").read_text())
    selected = config["selected"]
    if selected is None:
        raise ValueError("Choose models using dev benchmark first")
    connection = await connect(settings)
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() or None,
        timeout=60,
        check_compatibility=False,
    )
    try:
        await connection.execute("SELECT pg_advisory_lock(210025)")
        legacy_manifest = settings.index_storage_path / "chunks/manifest.json"
        manifest = (
            json.loads(legacy_manifest.read_text())
            if legacy_manifest.exists()
            else {"documents": []}
        )
        artifacts_by_id = {}
        chunk_config = {
            "tokenizer": selected["model"] + "@" + selected["revision"],
            "tokenizer_model_name": selected["name"],
            "max_tokens": selected["max_length"] - 32,
            "overlap_tokens": 16,
        }
        for entry in manifest["documents"]:
            path = settings.index_storage_path / "chunks" / entry["artifact"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("Parsing artifact checksum mismatch")
            artifact = json.loads(path.read_text("utf-8"))
            artifacts_by_id[artifact["document"]["document_id"]] = (entry, artifact)
        rows = await connection.fetch(
            """SELECT p.manifest_key,p.document_id FROM registry.parsing_revisions p
            JOIN registry.document_versions d ON d.active_parsing_revision=p.parsing_revision"""
        )
        for row in rows:
            key = row["manifest_key"]
            path = (
                settings.index_storage_path / key
                if key.startswith("registered/")
                else settings.index_storage_path / "chunks" / key
            )
            artifact = json.loads(path.read_text("utf-8"))
            entry = {"artifact": key, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            artifacts_by_id[str(row["document_id"])] = (entry, artifact)
        artifacts = [artifacts_by_id[key] for key in sorted(artifacts_by_id)]
        if not artifacts:
            raise ValueError("No registered parsing artifacts; parse originals first")
        chunks = []
        for _, artifact in artifacts:
            verify_artifact(artifact)
            row = await connection.fetchrow(
                "SELECT * FROM registry.document_versions WHERE document_id=$1",
                UUID(artifact["document"]["document_id"]),
            )
            if row["file_sha256"] != artifact["document"]["file_sha256"]:
                raise ValueError("Original changed before indexing")
            updates = {
                key: row[key]
                for key in (
                    "title",
                    "category",
                    "document_role",
                    "version_label",
                    "version_status",
                    "verification_status",
                    "legal_status",
                    "source_id",
                    "source_url",
                )
            }
            artifact["document"].update(updates)
            fingerprint, values = create_chunks(
                artifact["document"], artifact["parsing_revision"], artifact["blocks"], chunk_config
            )
            artifact.update(
                chunks=values,
                max_tokens=chunk_config["max_tokens"],
                chunking_fingerprint=fingerprint,
            )
            verify_artifact(artifact)
            chunks.extend(values)
        model = LocalModel(selected, settings.model_storage_path)
        cache = settings.index_storage_path / "all-vectors.npy"
        cache_meta = settings.index_storage_path / "all-vector-checksums.json"
        signatures = [[c["content_sha256"]] for c in chunks]
        previous = load_cache(cache, cache_meta, selected)
        missing = {
            tuple(key): chunk["text"]
            for key, chunk in zip(signatures, chunks, strict=True)
            if tuple(key) not in previous
        }
        if missing:
            encoded = model.encode(list(missing.values()))
            previous.update(zip(missing, encoded, strict=True))
        vectors = np.stack([previous[tuple(key)] for key in signatures])
        save_cache(cache, cache_meta, selected, signatures, vectors)
        if not np.isfinite(vectors).all():
            raise ValueError("Invalid vectors")
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(210024)")
            vocabulary = {
                r["token"]: r["dimension"]
                for r in await connection.fetch("SELECT * FROM registry.lexical_vocabulary")
            }
            for token in sorted({t for c in chunks for t in tokens(c["text"])} - vocabulary.keys()):
                dimension = max(vocabulary.values(), default=-1) + 1
                await connection.execute(
                    "INSERT INTO registry.lexical_vocabulary VALUES($1,$2)", token, dimension
                )
                vocabulary[token] = dimension
        average_length = sum(len(tokens(c["text"])) for c in chunks) / len(chunks)
        fingerprint = canonical_hash(
            {
                "model": selected,
                "chunk_ids": [c["chunk_id"] for c in chunks],
                "document_metadata": [a["document"] for _, a in artifacts],
                "vocabulary": vocabulary,
                "lexical": "bm25-tf-qdrant-idf-v1",
                "vectors_sha256": hashlib.sha256(vectors.tobytes()).hexdigest(),
            }
        )
        collection = "pinui_documents_" + fingerprint[:16]
        if not client.collection_exists(collection):
            client.create_collection(
                collection,
                vectors_config={
                    "dense": models.VectorParams(
                        size=selected["dimension"], distance=models.Distance.COSINE
                    )
                },
                sparse_vectors_config={
                    "lexical": models.SparseVectorParams(modifier=models.Modifier.IDF)
                },
                on_disk_payload=True,
            )
            for key in (
                "document_id",
                "document_family_id",
                "project_id",
                "index_generation_id",
                "category",
                "document_role",
                "version_status",
                "verification_status",
                "legal_status",
            ):
                client.create_payload_index(
                    collection, key, models.PayloadSchemaType.KEYWORD, wait=True
                )
        info = client.get_collection(collection)
        if info.config.params.vectors["dense"].size != selected["dimension"]:
            raise ValueError("Collection dimension mismatch")
        generations = []
        for entry, artifact in artifacts:
            document = artifact["document"]
            selected_chunks = [c for c in chunks if c["document_id"] == document["document_id"]]
            artifact["chunks"] = selected_chunks
            artifact["max_tokens"] = selected["max_length"] - 32
            artifact["chunking_fingerprint"] = selected_chunks[0]["chunking_fingerprint"]
            verify_artifact(artifact)
            await stage_artifact(connection, artifact, entry["artifact"], entry["sha256"])
            document_id = UUID(document["document_id"])
            generation = uuid5(document_id, fingerprint)
            generations.append((document_id, generation, len(selected_chunks)))
            async with connection.transaction():
                await connection.execute(
                    (
                        "INSERT INTO registry.index_generations\n                "
                        "    (generation_id,document_id,parsing_revision,fingerp"
                        "rint,collection_name,status,expected_count)\n           "
                        "         VALUES($1,$2,$3,$4,$5,'staging',$6) ON CONFLIC"
                        "T DO NOTHING"
                    ),
                    generation,
                    document_id,
                    UUID(artifact["parsing_revision"]),
                    fingerprint,
                    collection,
                    len(selected_chunks),
                )
            positions = {c["chunk_id"]: i for i, c in enumerate(chunks)}
            points = []
            for chunk in selected_chunks:
                point = uuid5(UUID(chunk["chunk_id"]), str(generation))
                payload = {k: v for k, v in chunk.items() if k not in ("text", "spans")}
                payload["index_generation_id"] = str(generation)
                lexical = sparse(chunk["text"], vocabulary, average_length)
                points.append(
                    models.PointStruct(
                        id=str(point),
                        payload=payload,
                        vector={
                            "dense": vectors[positions[chunk["chunk_id"]]].tolist(),
                            "lexical": models.SparseVector(**lexical),
                        },
                    )
                )
                await connection.execute(
                    (
                        "INSERT INTO registry.generation_chunks VALUES($1,$2,$3)"
                        " ON CONFLICT DO NOTHING"
                    ),
                    generation,
                    UUID(chunk["chunk_id"]),
                    point,
                )
            for offset in range(0, len(points), 64):
                client.upsert(collection, points[offset : offset + 64], wait=True)
            actual = client.retrieve(
                collection, [p.id for p in points], with_payload=True, with_vectors=True
            )
            lookup = {str(p.id): p.payload for p in actual}
            actual_vectors = {str(p.id): p.vector for p in actual}
            for point in points:
                stored = actual_vectors.get(str(point.id))
                if not stored or not np.allclose(stored["dense"], point.vector["dense"], atol=1e-6):
                    raise ValueError("Stored dense vector mismatch")
                lexical = stored["lexical"]
                if lexical.indices != point.vector["lexical"].indices or not np.allclose(
                    lexical.values, point.vector["lexical"].values, atol=1e-6
                ):
                    raise ValueError("Stored sparse vector mismatch")
            if len(lookup) != len(points) or any(
                lookup.get(str(p.id)) != p.payload for p in points
            ):
                raise ValueError("Incomplete or mismatched Qdrant points")
            await connection.execute(
                "UPDATE registry.index_generations SET verified_count=$2 WHERE generation_id=$1",
                generation,
                len(points),
            )
            print(
                json.dumps({"indexed": document["document_alias"], "points": len(points)}),
                flush=True,
            )
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(210024)")
            if os.environ.get("JOB_ID"):
                lease = await connection.fetchrow(
                    "SELECT * FROM registry.jobs WHERE job_id=$1 FOR UPDATE",
                    UUID(os.environ["JOB_ID"]),
                )
                alive = await connection.fetchval(
                    "SELECT lease_until>now() FROM registry.jobs WHERE job_id=$1",
                    UUID(os.environ["JOB_ID"]),
                )
                if (
                    not lease
                    or lease["attempt"] != int(os.environ["JOB_ATTEMPT"])
                    or lease["status"] != "running"
                    or lease["cancel_requested"]
                    or not alive
                ):
                    raise ValueError("Job lease expired before activation")
            for document_id, generation, expected in generations:
                row = await connection.fetchrow(
                    "SELECT * FROM registry.index_generations WHERE generation_id=$1 FOR UPDATE",
                    generation,
                )
                if row["verified_count"] != expected:
                    raise ValueError("Generation cannot be activated")
                if row["status"] != "active":
                    await connection.execute(
                        (
                            "UPDATE registry.index_generations SET status='retired' "
                            "WHERE document_id=$1 AND status='active'"
                        ),
                        document_id,
                    )
                    await connection.execute(
                        (
                            "UPDATE registry.index_generations SET status='active' W"
                            "HERE generation_id=$1"
                        ),
                        generation,
                    )
                    await connection.execute(
                        (
                            "UPDATE registry.document_versions SET active_index_generation_id=$2,"
                            "active_parsing_revision=(SELECT parsing_revision "
                            "FROM registry.index_generations WHERE generation_id=$2),"
                            "ingestion_status='ready',indexed_at=now() "
                            "WHERE document_id=$1"
                        ),
                        document_id,
                        generation,
                    )
                    await connection.execute(
                        (
                            "INSERT INTO registry.audit_events VALUES($1,$2,'generat"
                            "ion_activated',$3,now()) ON CONFLICT DO NOTHING"
                        ),
                        identity("activation:" + str(generation)),
                        document_id,
                        json.dumps({"generation_id": str(generation), "fingerprint": fingerprint}),
                    )
        aliases = client.get_aliases().aliases
        operations = []
        if any(a.alias_name == settings.qdrant_collection for a in aliases):
            operations.append(
                models.DeleteAliasOperation(
                    delete_alias=models.DeleteAlias(alias_name=settings.qdrant_collection)
                )
            )
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=collection, alias_name=settings.qdrant_collection
                )
            )
        )
        client.update_collection_aliases(operations)
        deployment = {
            "collection": collection,
            "fingerprint": fingerprint,
            "model": selected,
            "vocabulary": vocabulary,
            "average_length": average_length,
            "chunks": len(chunks),
            "reranker": config["reranker"],
            "reranker_length": config["reranker_length"],
        }
        manifest_path = Path("data/index-manifest.json")
        pending_manifest = manifest_path.with_suffix(".pending")
        pending_manifest.write_text(json.dumps(deployment, indent=2), encoding="utf-8")
        pending_manifest.replace(manifest_path)
        print(
            json.dumps(
                {
                    "active_documents": len(generations),
                    "points": len(chunks),
                    "collection": collection,
                }
            ),
            flush=True,
        )
    finally:
        client.close()
        await connection.close()


if __name__ == "__main__":
    asyncio.run(run())
