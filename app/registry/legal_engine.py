"""Deterministic clause compilation and conservative legal-currentness gate."""

import hashlib
import json
import operator
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.models.legal import CurrentClause, LawChain, LegalResult


def text_hash(text: str) -> str:
    # Exact source text: no hidden whitespace/RTL normalization of legal changes.
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_hash(value) -> str:
    return text_hash(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def evaluate_conditions(conditions, facts):
    checks = []
    missing = []
    functions = {
        "eq": operator.eq,
        "lt": operator.lt,
        "le": operator.le,
        "gt": operator.gt,
        "ge": operator.ge,
    }
    for condition in conditions:
        actual = facts.get(condition.field)
        expected = condition.value
        try:
            if condition.value_type == "date":
                if type(actual) is not str:
                    raise ValueError("ISO date required")
                actual, expected = date.fromisoformat(actual), date.fromisoformat(expected)
            elif condition.value_type == "integer" and type(actual) is not int:
                raise ValueError("Integer required")
            elif condition.value_type == "boolean" and type(actual) is not bool:
                raise ValueError("Boolean required")
            elif condition.value_type == "string" and type(actual) is not str:
                raise ValueError("String required")
            checks.append(functions[condition.operator](actual, expected))
        except (ValueError, TypeError):
            missing.append(condition.field)
    if False in checks:
        return False, ()
    return (None, tuple(sorted(set(missing)))) if missing else (True, ())


def evaluate_applicability(amendment, facts):
    base, missing_base = evaluate_conditions(amendment.conditions, facts)
    if base is False or not amendment.any_conditions:
        return base, missing_base
    alternatives = [evaluate_conditions(group, facts) for group in amendment.any_conditions]
    if any(value is True for value, _ in alternatives):
        return base, missing_base
    if all(value is False for value, _ in alternatives):
        return False, ()
    missing = set(missing_base) | {
        field for value, fields in alternatives if value is None for field in fields
    }
    return None, tuple(sorted(missing))


def compile_law(chain: LawChain, as_of: date, facts=None, *, now=None) -> LegalResult:
    facts = facts or {}
    now = now or datetime.now(UTC)

    def deny(status, missing=()):
        return LegalResult(
            law_slug=chain.law_slug, as_of=as_of, status=status, missing_facts=missing
        )

    review = chain.review
    present = set(chain.baseline_incorporated_ids) | {p.amendment_id for p in chain.amendments}
    if (
        not review.complete
        or review.verification_status != "verified"
        or chain.baseline_verification_status != "verified"
        or present != set(review.expected_amendment_ids)
        or any(
            p.verification_status != "verified" or p.effective_from is None
            for p in chain.amendments
        )
    ):
        return deny("chain_incomplete")
    if (
        review.checked_at > now
        or now >= review.next_check_at
        or not review.covered_from <= as_of <= review.checked_through
        or as_of > now.astimezone(ZoneInfo("Asia/Jerusalem")).date()
    ):
        return deny("freshness_unconfirmed")
    if as_of < chain.baseline_effective_from:
        return deny("not_yet_effective")
    clauses = [
        CurrentClause(
            clause_id=c.clause_id,
            text_he=c.text_he,
            text_sha256=text_hash(c.text_he),
            provenance=(c.source,),
        )
        for c in chain.clauses
    ]
    applied = []
    for amendment in sorted(chain.amendments, key=lambda p: (p.effective_from, p.sequence)):
        if amendment.effective_from > as_of or (
            amendment.effective_to is not None and as_of >= amendment.effective_to
        ):
            continue
        applicable, missing = evaluate_applicability(amendment, facts)
        if applicable is None:
            return deny("applicability_unknown", missing)
        if not applicable:
            continue
        for change in amendment.changes:
            if change.operation == "repeal_law":
                return deny("repealed")
            positions = {c.clause_id: i for i, c in enumerate(clauses)}
            if change.clause_id not in positions:
                return deny("version_conflict")
            position = positions[change.clause_id]
            previous = clauses[position]
            if previous.text_sha256 != change.expected_text_sha256:
                return deny("version_conflict")
            if change.operation == "delete":
                clauses.pop(position)
            elif change.operation == "replace":
                clauses[position] = CurrentClause(
                    clause_id=previous.clause_id,
                    text_he=change.new_text_he,
                    text_sha256=text_hash(change.new_text_he),
                    provenance=previous.provenance + (amendment.source,),
                    applied_amendment_ids=previous.applied_amendment_ids
                    + (amendment.amendment_id,),
                )
            elif change.operation == "insert_after":
                if change.new_clause_id in positions:
                    return deny("version_conflict")
                clauses.insert(
                    position + 1,
                    CurrentClause(
                        clause_id=change.new_clause_id,
                        text_he=change.new_text_he,
                        text_sha256=text_hash(change.new_text_he),
                        provenance=(amendment.source,),
                        applied_amendment_ids=(amendment.amendment_id,),
                    ),
                )
        applied.append(amendment.amendment_id)
    if not clauses:
        return deny("version_conflict")
    result = LegalResult(
        law_slug=chain.law_slug,
        as_of=as_of,
        status="verified",
        clauses=tuple(clauses),
        applied_amendment_ids=tuple(applied),
    )
    fingerprint = {
        "chain": chain.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "facts": facts,
        "compiler_revision": "legal-v1",
    }
    return result.model_copy(update={"snapshot_sha256": canonical_hash(fingerprint)})
