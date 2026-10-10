import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.main import create_app
from app.api.readiness import heartbeat_ready
from app.config.settings import Settings


def test_launch_without_llm_key():
    settings = Settings(_env_file=None, openai_api_key="")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["stage"] == "T01"
        assert response.headers["X-Request-ID"]


def test_dotenv_blank_options_and_false(tmp_path):
    dotenv = tmp_path / "test.env"
    dotenv.write_text("OPENAI_STORE=false\nEMBEDDING_DIMENSION=\nOPENAI_API_KEY=\n")
    settings = Settings(_env_file=dotenv)
    assert settings.openai_store is False
    assert settings.embedding_dimension is None
    assert not settings.llm_configured


def test_unavailable_dependencies_and_secret_redaction(tmp_path, monkeypatch):
    async def unavailable(settings):
        return False

    monkeypatch.setattr("app.api.readiness.check_postgres", unavailable)
    monkeypatch.setattr("app.api.readiness.check_qdrant", unavailable)
    settings = Settings(
        _env_file=None,
        openai_api_key="secret-key-marker",
        runtime_path=tmp_path,
        postgres_url="postgresql://user:secret-db-marker@localhost/db",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/status")
        assert response.status_code == 503
        body = response.json()
        assert body["capabilities"]["llm_configured"] is True
        assert body["capabilities"]["answer_generation"] is False
        assert body["capabilities"]["search_he"] is False
        assert body["components"]["job_processing"]["status"] == "not_implemented"
        assert "secret-key-marker" not in response.text
        assert "secret-db-marker" not in response.text


def test_error_envelope():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/v1/query")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
        assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_stale_heartbeat_is_not_ready(tmp_path):
    settings = Settings(_env_file=None, runtime_path=tmp_path)
    (tmp_path / "worker.heartbeat").write_text("0")
    assert not heartbeat_ready(settings, "worker")
    (tmp_path / "worker.heartbeat").write_text("invalid")
    assert not heartbeat_ready(settings, "worker")


@pytest.mark.parametrize(
    "overrides",
    [
        {"chunk_overlap_tokens": 800},
        {"job_heartbeat_seconds": 120},
        {"corpus_language": "ru"},
        {"openai_store": True},
        {"app_mode": "production"},
    ],
)
def test_invalid_configuration(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)
