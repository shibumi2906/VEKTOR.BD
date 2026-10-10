"""Personal-computer model settings; the stored secret cannot be retrieved."""

from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from app.services.errors import DomainError
from app.services.model_key import key_status, save_key

router = APIRouter(prefix="/settings/openai")


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value):
        key = value.get_secret_value().strip()
        if not 8 <= len(key) <= 512 or any(c.isspace() or ord(c) > 126 for c in key):
            raise ValueError("Invalid API key")
        return SecretStr(key)


def local_settings(request):
    settings = request.app.state.settings
    if settings.auth_mode != "local":
        raise DomainError("LOCAL_SETTINGS_ONLY", 403)
    return settings


async def check_key(settings, key):
    if not key:
        raise DomainError("LLM_NOT_CONFIGURED", 409)
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.get(
                "https://api.openai.com/v1/models/" + quote(settings.llm_model, safe=""),
                headers={"Authorization": "Bearer " + key},
            )
    except httpx.HTTPError as exc:
        raise DomainError("KEY_CHECK_UNAVAILABLE", 503) from exc
    codes = {
        401: "INVALID_API_KEY",
        403: "MODEL_ACCESS_DENIED",
        404: "MODEL_ACCESS_DENIED",
        429: "KEY_CHECK_RATE_LIMITED",
    }
    if response.status_code != 200:
        raise DomainError(codes.get(response.status_code, "KEY_CHECK_UNAVAILABLE"), 422)


@router.get("")
async def status(request: Request):
    return key_status(local_settings(request))


@router.post("")
async def configure(body: KeyInput, request: Request):
    settings = local_settings(request)
    key = body.api_key.get_secret_value()
    await check_key(settings, key)
    save_key(settings, key)
    return {**key_status(settings), "model_access": True}


@router.post("/check")
async def check_saved(request: Request):
    settings = local_settings(request)
    await check_key(settings, settings.openai_api_key.get_secret_value())
    return {**key_status(settings), "model_access": True}
