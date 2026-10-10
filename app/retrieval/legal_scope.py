"""Mandatory gate for the future question pipeline; denied scopes expose no text."""

import json
from dataclasses import dataclass

from app.registry.legal_repository import resolve_law


class LegalScopeBlocked(Exception):
    def __init__(self, results, code="LEGAL_CURRENTNESS_UNCONFIRMED"):
        self.code = code
        self.statuses = {r.law_slug: r.status for r in results if r.status != "verified"}
        self.missing_facts = sorted({f for r in results for f in r.missing_facts})
        super().__init__(self.code)


@dataclass(frozen=True)
class LegalScope:
    snapshots: tuple
    facts_json: str


async def prepare_legal_scope(connection, law_slugs, as_of=None, facts=None, *, now=None):
    if not law_slugs:
        raise ValueError("Explicit nonempty law scope required")
    # Consistent set across all requested laws; don't answer from a partly valid scope.
    async with connection.transaction(isolation="repeatable_read"):
        results = tuple(
            [
                await resolve_law(connection, slug, as_of, facts, now=now)
                for slug in sorted(set(law_slugs))
            ]
        )
        if any(result.status != "verified" for result in results):
            raise LegalScopeBlocked(results)
        return LegalScope(snapshots=results, facts_json=json.dumps(facts or {}, sort_keys=True))


async def revalidate_legal_scope(connection, scope, *, now=None):
    async with connection.transaction(isolation="repeatable_read"):
        for snapshot in scope.snapshots:
            current = await resolve_law(
                connection, snapshot.law_slug, snapshot.as_of, json.loads(scope.facts_json), now=now
            )
            if current.status != "verified":
                raise LegalScopeBlocked((current,))
            if current.snapshot_sha256 != snapshot.snapshot_sha256:
                raise LegalScopeBlocked((), code="SOURCE_CHANGED")


def validate_legal_hit(scope, *, law_slug, clause_id, snapshot_sha256, start, end, text_he):
    """A Qdrant hit can supply evidence only if it matches the selected current clause span."""
    for snapshot in scope.snapshots:
        if snapshot.law_slug != law_slug or snapshot.snapshot_sha256 != snapshot_sha256:
            continue
        for clause in snapshot.clauses:
            if clause.clause_id == clause_id:
                if (
                    type(start) is int
                    and type(end) is int
                    and 0 <= start < end <= len(clause.text_he)
                    and clause.text_he[start:end] == text_he
                ):
                    return clause.provenance
    raise ValueError("LEGAL_EVIDENCE_MISMATCH")


async def retrieve_current_legal_evidence(
    connection, law_slugs, search, as_of=None, facts=None, *, now=None
):
    """Call a retrieval adapter only after verification, then validate every returned span.

    Adapter receives the exact selected snapshots. This wrapper does not substitute an
    unimplemented vector backend or invoke an answer model without evidence.
    """
    scope = await prepare_legal_scope(connection, law_slugs, as_of, facts, now=now)
    hits = await search(scope)
    evidence = []
    for hit in hits:
        provenance = validate_legal_hit(scope, **hit)
        evidence.append({**hit, "provenance": provenance, "is_derived_text": True})
    await revalidate_legal_scope(connection, scope, now=now)
    if not evidence:
        raise ValueError("INSUFFICIENT_EVIDENCE")
    return scope, tuple(evidence)
