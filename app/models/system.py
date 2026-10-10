from typing import Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str


class ComponentStatus(BaseModel):
    status: Literal["ready", "unavailable", "not_implemented"]


class Capabilities(BaseModel):
    search_he: bool = False
    translation: bool = False
    answer_generation: bool = False
    topic_comparison: bool = False
    llm_configured: bool = False


class SystemStatus(BaseModel):
    request_id: str
    status: Literal["ready", "unavailable"]
    scope: Literal["bootstrap_infrastructure", "local_retrieval"] = "bootstrap_infrastructure"
    stage: Literal["T01", "local_retrieval"] = "T01"
    components: dict[str, ComponentStatus]
    capabilities: Capabilities
