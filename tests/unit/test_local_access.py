from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config.settings import Settings


class LocalDatabase:
    async def execute(self, *args):
        return "OK"

    async def fetch(self, *args):
        return []

    async def close(self):
        pass


def test_local_documents_open_without_token(monkeypatch):
    async def connect(settings):
        return LocalDatabase()

    monkeypatch.setattr("app.api.product.connect", connect)
    with TestClient(create_app(Settings(_env_file=None, auth_mode="local"))) as client:
        response = client.get("/documents")
        assert response.status_code == 200
        assert response.json()["documents"] == []
        assert (
            client.get("/documents", headers={"Origin": "https://foreign.example"}).status_code
            == 403
        )
        assert client.get("/documents", headers={"Host": "foreign.example"}).status_code == 403


def test_opt_in_token_mode_still_requires_token():
    with TestClient(create_app(Settings(_env_file=None, auth_mode="token"))) as client:
        response = client.get("/documents")
        assert response.status_code == 401
