import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.main import create_app
from app.api.model_settings import check_key
from app.config.settings import Settings
from app.services.errors import DomainError
from app.services.model_key import key_path

SYNTHETIC_KEY = "sk-synthetic-test-never-valid"


def settings(tmp_path, **kwargs):
    return Settings(
        _env_file=None,
        app_mode="bootstrap",
        runtime_path=tmp_path,
        openai_api_key=SecretStr(""),
        **kwargs,
    )


def test_save_restore_and_response_never_return_secret(tmp_path, monkeypatch):
    config = settings(tmp_path)
    checked = []

    async def check(configuration, key):
        checked.append(key)

    monkeypatch.setattr("app.api.model_settings.check_key", check)
    client = TestClient(create_app(config))
    assert not client.get("/settings/openai").json()["configured"]
    result = client.post("/settings/openai", json={"api_key": SYNTHETIC_KEY})
    assert result.status_code == 200
    assert checked == [SYNTHETIC_KEY]
    assert SYNTHETIC_KEY not in result.text
    assert config.openai_api_key.get_secret_value() == SYNTHETIC_KEY
    stored = json.loads(key_path(config).read_text())
    if os.name == "nt":
        assert "api_key_dpapi" in stored
        assert SYNTHETIC_KEY not in key_path(config).read_text()
    else:
        assert stored["api_key"] == SYNTHETIC_KEY
    restarted = create_app(settings(tmp_path))
    assert restarted.state.settings.openai_api_key.get_secret_value() == SYNTHETIC_KEY
    assert SYNTHETIC_KEY not in TestClient(restarted).get("/settings/openai").text
    assert client.post("/settings/openai/check").json()["model_access"]


def test_rejected_replacement_keeps_current_key(tmp_path, monkeypatch):
    config = settings(tmp_path)
    config.openai_api_key = SecretStr(SYNTHETIC_KEY)

    async def check(*args):
        raise DomainError("INVALID_API_KEY", 422)

    monkeypatch.setattr("app.api.model_settings.check_key", check)
    result = TestClient(create_app(config)).post(
        "/settings/openai", json={"api_key": "sk-invalid-test-key"}
    )
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "INVALID_API_KEY"
    assert config.openai_api_key.get_secret_value() == SYNTHETIC_KEY
    assert not key_path(config).exists()
    assert "sk-invalid-test-key" not in result.text


def test_invalid_input_foreign_origin_and_nonlocal_mode(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))
    result = client.post("/settings/openai", json={"api_key": "private value\n"})
    assert result.status_code == 422
    assert "private value" not in result.text
    assert (
        client.post(
            "/settings/openai",
            json={"api_key": SYNTHETIC_KEY},
            headers={"Origin": "https://example.com"},
        ).status_code
        == 403
    )
    token_client = TestClient(create_app(settings(tmp_path, auth_mode="token")))
    assert token_client.get("/settings/openai").status_code == 403


@pytest.mark.parametrize(
    "code,expected",
    [
        (401, "INVALID_API_KEY"),
        (403, "MODEL_ACCESS_DENIED"),
        (404, "MODEL_ACCESS_DENIED"),
        (429, "KEY_CHECK_RATE_LIMITED"),
    ],
)
async def test_model_check_maps_errors_without_response_body(tmp_path, monkeypatch, code, expected):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers):
            assert url == "https://api.openai.com/v1/models/gpt-5.4-mini"
            assert headers["Authorization"] == "Bearer " + SYNTHETIC_KEY
            return httpx.Response(code, text=SYNTHETIC_KEY)

    monkeypatch.setattr("app.api.model_settings.httpx.AsyncClient", lambda **kw: Client())
    with pytest.raises(DomainError) as error:
        await check_key(settings(tmp_path), SYNTHETIC_KEY)
    assert error.value.code == expected
    assert SYNTHETIC_KEY not in str(error.value)
