from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)
    response_mode: Literal["auto", "answer", "search"] = "auto"
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    project_id: UUID | None = None
    document_family_id: UUID | None = None
    category: str | None = None
    mode: Literal["all_documents", "current_norms", "project_documents", "historical"] | None = None
    include_shared_norms: bool = False
    as_of: date | None = None
    language: str = "auto"
    debug: bool = False
    law_slugs: list[str] = Field(default_factory=list, max_length=20)
    applicability_facts: dict = Field(default_factory=dict)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)
    document_a: UUID
    document_b: UUID
    language: str = "auto"
    debug: bool = False
