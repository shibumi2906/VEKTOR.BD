from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    title: str = Field(min_length=1, max_length=300)


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["reader"] = "reader"
    enabled: bool


class UploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    family_slug: str = Field(pattern=r"^[a-z0-9.-]{1,100}$")
    title: str = Field(min_length=1, max_length=300)
    version_label: str = Field(min_length=1, max_length=80)
    document_role: Literal["draft_contract", "contract", "signed_contract", "reference"]
    category: Literal["contract", "reference"] = "contract"


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID
