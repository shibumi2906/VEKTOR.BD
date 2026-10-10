"""Export only non-secret runtime settings for the Windows package."""

import json
from pathlib import Path

from app.config.settings import Settings

FIELDS = (
    "app_mode",
    "auth_mode",
    "supported_query_languages",
    "embedding_model",
    "embedding_revision",
    "embedding_dimension",
    "reranker_model",
    "reranker_revision",
    "rerank_min_score",
    "max_context_tokens",
    "max_output_tokens",
    "query_cost_limit",
    "topic_compare_cost_limit",
    "daily_cost_limit",
    "llm_model",
    "llm_fallback_model",
    "chunk_max_tokens",
    "chunk_overlap_tokens",
    "query_timeout_seconds",
    "job_lease_seconds",
    "job_heartbeat_seconds",
    "provider_max_attempts",
)


def main():
    settings = Settings()
    config = {key: getattr(settings, key) for key in FIELDS}
    config.update(
        app_mode="production",
        auth_mode="local",
        ocr_runtime_signature="tesseract-5.5.3-heb-fast4.1-300dpi-v1",
    )
    destination = Path("data/windows-build/desktop-config.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Exported non-secret desktop configuration")


if __name__ == "__main__":
    main()
