"""Synthetic legal text only; these fixtures never establish a real law's validity."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.models.legal import LawChain
from app.registry.legal_engine import compile_law, text_hash
from app.retrieval.legal_scope import LegalScope, validate_legal_hit
from tests.fixtures.legal_cases import NEW, NOW, OLD, chain_data


def result(data=None, on="2026-10-09", facts=None, now=NOW):
    return compile_law(
        LawChain.model_validate(data or chain_data()), date.fromisoformat(on), facts, now=now
    )


@pytest.mark.parametrize("on,text", [("2025-12-31", OLD), ("2026-01-01", NEW)])
def test_effective_date_and_clause_sources(on, text):
    snapshot = result(on=on)
    assert snapshot.status == "verified"
    assert snapshot.clauses[0].text_he == text
    assert len(snapshot.clauses[0].provenance) == (2 if text == NEW else 1)
    assert snapshot.snapshot_sha256
    assert snapshot.is_derived_text


def test_future_amendment_never_changes_current_text():
    data = chain_data()
    data["amendments"][0]["effective_from"] = "2027-01-01"
    assert result(data).clauses[0].text_he == OLD


def test_or_transition_conditions_do_not_apply_twice_or_guess_missing_facts():
    data = chain_data()
    data["amendments"][0]["any_conditions"] = [
        [{"field": "new_contract", "value_type": "boolean", "operator": "eq", "value": True}],
        [{"field": "special_regime", "value_type": "boolean", "operator": "eq", "value": True}],
    ]
    assert result(data).status == "applicability_unknown"
    snapshot = result(data, facts={"new_contract": True, "special_regime": True})
    assert snapshot.clauses[0].text_he == NEW
    assert snapshot.applied_amendment_ids == ("change_1",)
    assert (
        result(data, facts={"new_contract": False, "special_regime": False}).clauses[0].text_he
        == OLD
    )
    assert result(data, facts={"new_contract": False}).status == "applicability_unknown"


def test_not_yet_effective_baseline_is_not_active():
    data = chain_data()
    data["review"]["covered_from"] = "2024-12-01"
    assert result(data, on="2024-12-31").status == "not_yet_effective"


@pytest.mark.parametrize("edit", ["missing", "extra", "unknown_date", "unverified", "incomplete"])
def test_incomplete_inventory_exposes_no_text(edit):
    data = chain_data()
    if edit == "missing":
        data["review"]["expected_amendment_ids"].append("missing_change")
    if edit == "extra":
        data["review"]["expected_amendment_ids"] = []
    if edit == "unknown_date":
        data["amendments"][0]["effective_from"] = None
    if edit == "unverified":
        data["amendments"][0]["verification_status"] = "manual_review"
    if edit == "incomplete":
        data["review"]["complete"] = False
    snapshot = result(data)
    assert snapshot.status == "chain_incomplete"
    assert not snapshot.clauses and snapshot.snapshot_sha256 is None


def test_wrong_preceding_text_cannot_apply_amendment():
    data = chain_data()
    data["amendments"][0]["changes"][0]["expected_text_sha256"] = "b" * 64
    assert result(data).status == "version_conflict"
    assert not result(data).clauses


def test_unknown_or_invalid_transition_fact_blocks_answer():
    data = chain_data()
    data["amendments"][0]["conditions"] = [
        {
            "field": "contract_signed_on",
            "value_type": "date",
            "operator": "ge",
            "value": "2026-01-01",
        }
    ]
    missing = result(data)
    assert missing.status == "applicability_unknown"
    assert missing.missing_facts == ("contract_signed_on",)
    assert not missing.clauses
    assert result(data, facts={"contract_signed_on": "invalid"}).status == "applicability_unknown"
    assert result(data, facts={"contract_signed_on": "2025-08-01"}).clauses[0].text_he == OLD
    assert result(data, facts={"contract_signed_on": "2026-01-01"}).clauses[0].text_he == NEW


def test_temporary_amendment_expires_at_exclusive_upper_bound():
    data = chain_data()
    data["amendments"][0]["effective_to"] = "2026-05-01"
    assert result(data, on="2026-04-30").clauses[0].text_he == NEW
    assert result(data, on="2026-05-01").clauses[0].text_he == OLD


def test_repeal_law_prevents_current_answer():
    data = chain_data()
    data["amendments"][0]["changes"] = [{"operation": "repeal_law", "clause_id": "law"}]
    assert result(data).status == "repealed"
    assert not result(data).clauses
    assert result(data, on="2025-12-31").status == "verified"


def test_insertion_deletion_and_order_keep_correct_sources():
    data = chain_data()
    data["amendments"][0]["changes"] = [
        {
            "operation": "insert_after",
            "clause_id": "1",
            "new_clause_id": "1a",
            "expected_text_sha256": text_hash(OLD),
            "new_text_he": NEW,
        },
        {"operation": "delete", "clause_id": "1", "expected_text_sha256": text_hash(OLD)},
    ]
    snapshot = result(data)
    assert [c.clause_id for c in snapshot.clauses] == ["1a"]
    assert snapshot.clauses[0].provenance[0].clause == "2"


@pytest.mark.parametrize(
    "on,now",
    [
        ("2024-12-31", NOW),
        ("2026-10-10", NOW),
        ("2026-10-09", datetime(2026, 10, 10, 10, tzinfo=UTC)),
        ("2026-10-09", datetime(2026, 10, 9, 9, tzinfo=UTC)),
    ],
)
def test_uncovered_date_expired_or_future_verification_blocks(on, now):
    assert result(on=on, now=now).status == "freshness_unconfirmed"


def test_hebrew_current_day_uses_jerusalem_not_utc():
    data = chain_data()
    data["review"]["checked_at"] = "2026-10-08T12:00:00Z"
    assert result(data, now=datetime(2026, 10, 8, 22, tzinfo=UTC)).status == "verified"


def test_snapshots_are_reproducible_and_date_specific():
    assert result().snapshot_sha256 == result().snapshot_sha256
    assert result(on="2025-12-31").snapshot_sha256 != result().snapshot_sha256


def test_double_application_and_ambiguous_order_rejected():
    data = chain_data()
    data["baseline_incorporated_ids"] = ["change_1"]
    with pytest.raises(ValidationError):
        LawChain.model_validate(data)
    data = chain_data()
    data["amendments"].append({**data["amendments"][0], "amendment_id": "change_2"})
    with pytest.raises(ValidationError):
        LawChain.model_validate(data)


def test_retrieval_hit_must_match_current_snapshot_and_exact_span():
    snapshot = result()
    scope = LegalScope(snapshots=(snapshot,), facts_json="{}")
    params = {
        "law_slug": snapshot.law_slug,
        "clause_id": "1",
        "snapshot_sha256": snapshot.snapshot_sha256,
        "start": 0,
        "end": len(NEW),
        "text_he": NEW,
    }
    assert len(validate_legal_hit(scope, **params)) == 2
    for override in (
        {"text_he": OLD},
        {"snapshot_sha256": "0" * 64},
        {"law_slug": "different_law"},
        {"start": -1},
        {"end": True},
    ):
        with pytest.raises(ValueError, match="MISMATCH"):
            validate_legal_hit(scope, **(params | override))
