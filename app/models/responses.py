from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CitationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    citation_id: UUID
    document_id: UUID
    chunk_id: UUID
    block_id: UUID
    span_start: int = Field(ge=0)
    span_end: int = Field(gt=0)
    quote: str
    quote_translation: str | None = None
    quote_excerpt: str | None = None
    title_translation: str | None = None
    quote_translation_error: str | None = None
    locator: dict
    title: str
    issuer: str
    category: str
    verification_status: str


class ClaimResponse(BaseModel):
    claim_id: str
    text: str
    citation_ids: list[UUID]


class QueryResponse(BaseModel):
    request_id: UUID
    status: Literal["answered", "search_results", "insufficient_evidence", "clarification_required"]
    language: str
    answer: str | None
    claims: list[ClaimResponse]
    sources: list[CitationResponse]
    warnings: list[str]
    clarification_candidates: list[dict]
    usage: list[dict]
    debug_trace: dict | None


class FindingResponse(BaseModel):
    topic: str
    statement_a: str | None
    statement_b: str | None
    difference: str | None
    citations_a: list[CitationResponse]
    citations_b: list[CitationResponse]
    evidence_status_a: Literal["found", "not_found_in_retrieval"]
    evidence_status_b: Literal["found", "not_found_in_retrieval"]


class CompareResponse(BaseModel):
    request_id: UUID
    status: Literal["compared", "insufficient_evidence", "clarification_required"]
    language: str | None = None
    findings: list[FindingResponse]
    usage: list[dict]
    warnings: list[str] = Field(default_factory=list)
    clarification_topics: list[str] = Field(default_factory=list)
    snapshots: list[list[str]] = Field(default_factory=list)
