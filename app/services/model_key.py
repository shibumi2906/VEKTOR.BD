"""Local model credentials; never included in API responses or build artifacts."""

import json
import os
import tempfile
from datetime import UTC, datetime

from pydantic import SecretStr

from app.services.errors import DomainError


def key_path(settings):
    return settings.runtime_path / "openai-key.json"


def restore_key(settings):
    if settings.auth_mode != "local":
        return
    try:
        saved = json.loads(key_path(settings).read_text(encoding="utf-8"))
        key = saved.get("api_key")
        if os.name == "nt" and saved.get("api_key_dpapi"):
            from app.services.windows_secret import unprotect_key

            key = unprotect_key(saved["api_key_dpapi"])
        if isinstance(key, str) and key:
            settings.openai_api_key = SecretStr(key)
    except (OSError, ValueError, AttributeError):
        # A damaged local file must not prevent Hebrew search from starting.
        pass


def save_key(settings, key):
    path = key_path(settings)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        credential = {"api_key": key}
        if os.name == "nt":
            from app.services.windows_secret import protect_key

            credential = {"api_key_dpapi": protect_key(key)}
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".openai-key-", delete=False
        ) as file:
            temporary = file.name
            os.chmod(temporary, 0o600)
            json.dump(
                {
                    **credential,
                    "model": settings.llm_model,
                    "checked_at": datetime.now(UTC).isoformat(),
                },
                file,
            )
        os.replace(temporary, path)
    except OSError as exc:
        raise DomainError("KEY_SAVE_FAILED", 503) from exc
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    settings.openai_api_key = SecretStr(key)


def key_status(settings):
    return {
        "enabled": settings.auth_mode == "local",
        "configured": settings.llm_configured,
        "model": settings.llm_model,
    }
