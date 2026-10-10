import pytest

from app.config.settings import Settings


@pytest.fixture(autouse=True)
def isolate_runtime_environment(monkeypatch):
    # Unit tests explicitly construct configuration. Compose production env must not leak in.
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
