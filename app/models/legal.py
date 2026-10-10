"""Reviewed, structured legal changes. PDF prose is never an executable amendment."""

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class LegalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(LegalModel):
    title: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    url: HttpUrl
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_date: date
    page: int | None = Field(default=None, gt=0)
    clause: str = Field(min_length=1)
    source_type: Literal["official"] = "official"

    @model_validator(mode="after")
    def source_url(self):
        if self.url.scheme != "https" or self.url.username or self.url.password:
            raise ValueError("Evidence requires a public HTTPS original without credentials")
        return self


class BaseClause(LegalModel):
    clause_id: str = Field(min_length=1)
    text_he: str = Field(min_length=1)
    source: Evidence

    @model_validator(mode="after")
    def hebrew(self):
        if not re.search(r"[\u05d0-\u05ea]", self.text_he):
            raise ValueError("Law text must be Hebrew")
        return self


class Condition(LegalModel):
    field: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    value_type: Literal["date", "integer", "boolean", "string"]
    operator: Literal["eq", "lt", "le", "gt", "ge"]
    value: str | int | bool

    @model_validator(mode="after")
    def typed_value(self):
        if self.value_type == "date":
            if not isinstance(self.value, str):
                raise ValueError("Date conditions use ISO dates")
            date.fromisoformat(self.value)
        if self.value_type == "integer" and type(self.value) is not int:
            raise ValueError("Integer condition requires integer")
        if self.value_type == "boolean" and type(self.value) is not bool:
            raise ValueError("Boolean condition requires boolean")
        if self.value_type == "string" and type(self.value) is not str:
            raise ValueError("String condition requires string")
        if self.value_type in ("boolean", "string") and self.operator != "eq":
            raise ValueError("Only equality is supported for boolean/string conditions")
        return self


class Change(LegalModel):
    operation: Literal["replace", "delete", "insert_after", "repeal_law"]
    clause_id: str = Field(min_length=1)
    expected_text_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    new_text_he: str | None = None
    new_clause_id: str | None = None

    @model_validator(mode="after")
    def operation_shape(self):
        if self.operation != "repeal_law" and not self.expected_text_sha256:
            raise ValueError("Every clause change requires the expected preceding text hash")
        if self.operation in ("replace", "insert_after"):
            if not self.new_text_he or not re.search(r"[\u05d0-\u05ea]", self.new_text_he):
                raise ValueError("Replacement text must be Hebrew")
        elif self.new_text_he is not None:
            raise ValueError("Deletion/repeal cannot contain replacement text")
        if (self.operation == "insert_after") != (self.new_clause_id is not None):
            raise ValueError("Only insertion requires a new clause ID")
        return self


class Amendment(LegalModel):
    amendment_id: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    effective_from: date | None
    effective_to: date | None = None
    verification_status: Literal["verified", "pending", "manual_review", "failed"]
    conditions: tuple[Condition, ...] = ()
    any_conditions: tuple[tuple[Condition, ...], ...] = ()
    changes: tuple[Change, ...] = Field(min_length=1)
    source: Evidence

    @model_validator(mode="after")
    def interval(self):
        if self.effective_to and self.effective_from and self.effective_to <= self.effective_from:
            raise ValueError("Invalid amendment interval")
        if any(not group for group in self.any_conditions):
            raise ValueError("An OR branch cannot be empty")
        return self


class ChainReview(LegalModel):
    verification_status: Literal["verified", "pending", "manual_review", "failed"]
    complete: bool
    covered_from: date
    checked_through: date
    checked_at: datetime
    next_check_at: datetime
    reviewed_by: str = Field(min_length=1)
    inventory_source: Evidence
    expected_amendment_ids: tuple[str, ...]

    @model_validator(mode="after")
    def coverage(self):
        if self.covered_from > self.checked_through:
            raise ValueError("Invalid coverage interval")
        if self.checked_at.utcoffset() is None or self.next_check_at.utcoffset() is None:
            raise ValueError("Review timestamps must include timezone")
        if self.next_check_at <= self.checked_at:
            raise ValueError("Next check must follow verification")
        if len(set(self.expected_amendment_ids)) != len(self.expected_amendment_ids):
            raise ValueError("Duplicate inventory amendment ID")
        return self


class LawChain(LegalModel):
    law_slug: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    title_he: str = Field(min_length=1)
    baseline_effective_from: date
    baseline_verification_status: Literal["verified", "pending", "manual_review", "failed"]
    baseline_incorporated_ids: tuple[str, ...] = ()
    clauses: tuple[BaseClause, ...] = Field(min_length=1)
    amendments: tuple[Amendment, ...] = ()
    review: ChainReview

    @model_validator(mode="after")
    def identities(self):
        clause_ids = [clause.clause_id for clause in self.clauses]
        patch_ids = [patch.amendment_id for patch in self.amendments]
        if len(set(clause_ids)) != len(clause_ids) or len(set(patch_ids)) != len(patch_ids):
            raise ValueError("Duplicate clause/amendment ID")
        if len({patch.sequence for patch in self.amendments}) != len(self.amendments):
            raise ValueError("Amendment ordering must be explicit and unambiguous")
        included = self.baseline_incorporated_ids
        if len(set(included)) != len(included) or set(included) & set(patch_ids):
            raise ValueError("Amendment cannot be included in baseline and applied again")
        if any(
            p.effective_from and p.effective_from < self.baseline_effective_from
            for p in self.amendments
        ):
            raise ValueError("Pre-baseline amendments must be incorporated into baseline")
        return self


class CurrentClause(LegalModel):
    clause_id: str
    text_he: str
    text_sha256: str
    provenance: tuple[Evidence, ...]
    applied_amendment_ids: tuple[str, ...] = ()


class LegalResult(LegalModel):
    law_slug: str
    as_of: date
    status: Literal[
        "verified",
        "chain_incomplete",
        "freshness_unconfirmed",
        "applicability_unknown",
        "version_conflict",
        "not_yet_effective",
        "repealed",
    ]
    clauses: tuple[CurrentClause, ...] = ()
    applied_amendment_ids: tuple[str, ...] = ()
    missing_facts: tuple[str, ...] = ()
    snapshot_sha256: str | None = None
    is_derived_text: Literal[True] = True
