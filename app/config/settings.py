from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: Literal["bootstrap", "production"] = "bootstrap"
    app_timezone: Literal["Asia/Jerusalem"] = "Asia/Jerusalem"
    corpus_language: Literal["he"] = "he"
    supported_query_languages: list[str] = Field(default_factory=lambda: ["he", "ru"])
    postgres_url: SecretStr = SecretStr("")
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_collection: str = "pinui_documents"
    raw_storage_path: Path = Path("data/raw")
    runtime_path: Path = Path("runtime")
    model_storage_path: Path = Path("data/models")
    index_storage_path: Path = Path("data")
    openai_api_key: SecretStr = SecretStr("")
    openai_store: Literal[False] = False
    llm_provider: Literal["openai"] = "openai"
    llm_model: str = "gpt-5.4-mini"
    llm_fallback_model: str = "gpt-4.1-mini"
    embedding_provider: Literal["local"] = "local"
    embedding_model: str = ""
    embedding_revision: str = ""
    embedding_dimension: int | None = Field(default=None, gt=0)
    reranker_provider: Literal["local"] = "local"
    reranker_model: str = ""
    reranker_revision: str = ""
    rerank_min_score: float | None = None
    max_context_tokens: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    query_cost_limit: float | None = Field(default=None, gt=0)
    topic_compare_cost_limit: float | None = Field(default=None, gt=0)
    daily_cost_limit: float = Field(default=1.0, gt=0)
    admin_api_token: SecretStr = SecretStr("")
    reader_api_token: SecretStr = SecretStr("")
    auth_mode: Literal["local", "token"] = "local"
    enable_debug: bool = False
    chunk_max_tokens: int = Field(default=800, gt=0)
    chunk_overlap_tokens: int = Field(default=100, ge=0)
    dense_top_k: int = Field(default=30, gt=0)
    sparse_top_k: int = Field(default=30, gt=0)
    retrieval_top_k: int = Field(default=30, gt=0)
    rerank_top_k: int = Field(default=7, gt=0)
    max_query_variants: int = Field(default=3, ge=1, le=3)
    max_upload_bytes: int = Field(default=52428800, gt=0)
    query_timeout_seconds: int = Field(default=90, gt=0)
    job_lease_seconds: int = Field(default=120, gt=0)
    job_heartbeat_seconds: int = Field(default=30, gt=0)
    provider_max_attempts: int = Field(default=3, gt=0)
    worker_concurrency: int = Field(default=1, gt=0)
    ocr_runtime_signature: str = "tesseract-5.3.0-heb-300dpi-v1"
    use_query_expansion: bool = True
    use_hybrid_search: bool = True
    use_reranker: bool = True

    @field_validator("openai_store", mode="before")
    @classmethod
    def parse_store_false(cls, value):
        if isinstance(value, str) and value.casefold() in {"false", "0"}:
            return False
        return value

    @field_validator(
        "embedding_dimension",
        "rerank_min_score",
        "max_context_tokens",
        "max_output_tokens",
        "query_cost_limit",
        "topic_compare_cost_limit",
        mode="before",
    )
    @classmethod
    def blank_optional(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_configuration(self):
        if not {"he", "ru"}.issubset(self.supported_query_languages):
            raise ValueError("SUPPORTED_QUERY_LANGUAGES must contain he and ru")
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            raise ValueError("Chunk overlap must be smaller than chunk size")
        if self.job_heartbeat_seconds >= self.job_lease_seconds:
            raise ValueError("Heartbeat must be shorter than lease")
        if self.app_mode == "production":
            required = (
                self.postgres_url.get_secret_value(),
                self.embedding_model,
                self.embedding_revision,
                self.embedding_dimension,
                self.reranker_model,
                self.reranker_revision,
            )
            if not all(required) or self.rerank_min_score is None:
                raise ValueError("Production requires configured database and local models")
            if not self.use_hybrid_search or not self.use_reranker:
                raise ValueError("Production requires hybrid search and reranking")
        return self

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key.get_secret_value())
