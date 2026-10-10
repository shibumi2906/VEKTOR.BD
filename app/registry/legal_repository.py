"""Local administrative writes, auditable chain selection, and immutable snapshots."""

import json
from datetime import UTC, date, datetime
from urllib.parse import unquote
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.models.legal import LawChain, LegalResult
from app.registry.corpus import identity
from app.registry.legal_engine import canonical_hash, compile_law


async def register_law(connection, slug, title_he):
    law_id = identity("law:" + slug)
    await connection.execute(
        """INSERT INTO registry.legal_laws(law_id,slug,title_he) VALUES($1,$2,$3)
        ON CONFLICT(slug) DO NOTHING""",
        law_id,
        slug,
        title_he,
    )
    return law_id


async def save_chain(connection, chain: LawChain):
    """Administrator-reviewed input only. Selection is not confirmation or indexing."""
    payload = chain.model_dump(mode="json")
    digest = canonical_hash(payload)
    chain_id = identity("legal-chain:" + chain.law_slug + ":" + digest)
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock(210022)")
        authorities = await connection.fetch(
            "SELECT metadata FROM registry.source_registry WHERE source_type='official'"
        )
        allowlists = [json.loads(row["metadata"]) for row in authorities]
        evidence = [clause.source for clause in chain.clauses]
        evidence += [patch.source for patch in chain.amendments] + [chain.review.inventory_source]
        for source in evidence:
            path = unquote(source.url.path or "/")
            if ".." in path.split("/") or "\\" in path:
                raise ValueError("Invalid evidence path")
            if not any(
                source.url.host in entry.get("allowed_hosts", [])
                and any(
                    path.startswith(prefix) for prefix in entry.get("allowed_path_prefixes", [])
                )
                for entry in allowlists
            ):
                raise ValueError("Evidence is outside registered official sources")
        law_id = await register_law(connection, chain.law_slug, chain.title_he)
        review = chain.review
        await connection.execute(
            """INSERT INTO registry.legal_chains
            (chain_id,law_id,input_sha256,verification_status,covered_from,checked_through,
            checked_at,next_check_at,payload) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT DO NOTHING""",
            chain_id,
            law_id,
            digest,
            review.verification_status,
            review.covered_from,
            review.checked_through,
            review.checked_at,
            review.next_check_at,
            json.dumps(payload),
        )
        for amendment in chain.amendments:
            await connection.execute(
                """INSERT INTO registry.legal_amendments
                (chain_id,amendment_id,sequence,effective_from,effective_to,payload)
                VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING""",
                chain_id,
                amendment.amendment_id,
                amendment.sequence,
                amendment.effective_from,
                amendment.effective_to,
                amendment.model_dump_json(),
            )
        previous = await connection.fetchval(
            "SELECT current_chain_id FROM registry.legal_laws WHERE law_id=$1 FOR UPDATE", law_id
        )
        if previous != chain_id:
            await connection.execute(
                "UPDATE registry.legal_laws SET current_chain_id=$1 WHERE law_id=$2",
                chain_id,
                law_id,
            )
            await connection.execute(
                "INSERT INTO registry.audit_events VALUES($1,null,'legal_chain_selected',$2,now())",
                uuid4(),
                json.dumps(
                    {
                        "law_id": str(law_id),
                        "chain_id": str(chain_id),
                        "previous_chain_id": str(previous) if previous else None,
                        "reviewed_by": review.reviewed_by,
                    }
                ),
            )
    return chain_id


async def resolve_law(connection, slug, as_of: date | None = None, facts=None, *, now=None):
    now = now or datetime.now(UTC)
    as_of = as_of or now.astimezone(ZoneInfo("Asia/Jerusalem")).date()
    async with connection.transaction():
        # Prevent a concurrent selector replacing the chain while preparing this snapshot.
        row = await connection.fetchrow(
            """SELECT l.current_chain_id,c.payload FROM registry.legal_laws l
            LEFT JOIN registry.legal_chains c ON c.chain_id=l.current_chain_id
            WHERE l.slug=$1 FOR SHARE OF l""",
            slug,
        )
        if not row or not row["payload"]:
            return LegalResult(law_slug=slug, as_of=as_of, status="chain_incomplete")
        chain = LawChain.model_validate_json(row["payload"])
        result = compile_law(chain, as_of, facts, now=now)
        if result.status == "verified":
            await connection.execute(
                """INSERT INTO registry.legal_snapshots
                (snapshot_sha256,chain_id,as_of,facts_sha256,payload)
                VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING""",
                result.snapshot_sha256,
                row["current_chain_id"],
                as_of,
                canonical_hash(facts or {}),
                result.model_dump_json(),
            )
        return result
