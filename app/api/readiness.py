import asyncio
import json
import time

import asyncpg
import httpx

from app.config.settings import Settings
from app.models.system import Capabilities, ComponentStatus, SystemStatus


async def check_postgres(settings: Settings) -> bool:
    dsn = settings.postgres_url.get_secret_value()
    if not dsn:
        return False
    connection = None
    try:
        connection = await asyncpg.connect(
            dsn.replace("postgresql+asyncpg://", "postgresql://", 1), timeout=3
        )
        return await connection.fetchval("SELECT 1", timeout=3) == 1
    except (OSError, TimeoutError, asyncpg.PostgresError, ValueError):
        return False
    finally:
        if connection is not None:
            await connection.close(timeout=1)


async def check_qdrant(settings: Settings) -> bool:
    headers = {}
    if settings.qdrant_api_key.get_secret_value():
        headers["api-key"] = settings.qdrant_api_key.get_secret_value()
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(
                settings.qdrant_url.rstrip("/") + "/readyz", headers=headers
            )
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def heartbeat_ready(settings: Settings, role: str) -> bool:
    try:
        stamp = float((settings.runtime_path / f"{role}.heartbeat").read_text())
        return 0 <= time.time() - stamp < settings.job_heartbeat_seconds * 3
    except (OSError, ValueError):
        return False


async def build_status(settings: Settings, request_id: str) -> SystemStatus:
    postgres, qdrant = await asyncio.gather(check_postgres(settings), check_qdrant(settings))
    checks = {
        "postgres": postgres,
        "qdrant": qdrant,
        "worker_process": heartbeat_ready(settings, "worker"),
        "scheduler_process": heartbeat_ready(settings, "scheduler"),
        "config": True,
    }
    components = {
        name: ComponentStatus(status="ready" if ready else "unavailable")
        for name, ready in checks.items()
    }
    for name in ("local_models", "retrieval", "job_processing", "translation", "generation"):
        components[name] = ComponentStatus(status="not_implemented")
    local_ready = False
    if settings.app_mode == "production":
        try:
            manifest = json.loads((settings.index_storage_path / "index-manifest.json").read_text())
            local_ready = (
                all(
                    (settings.model_storage_path / m["name"] / m["onnx"]).is_file()
                    for m in (manifest["model"], manifest["reranker"])
                )
                and manifest["chunks"] > 0
            )
        except (OSError, KeyError, ValueError):
            local_ready = False
        checks["local_models"] = local_ready
        for name in ("local_models", "retrieval"):
            components[name] = ComponentStatus(status="ready" if local_ready else "unavailable")
        components["job_processing"] = ComponentStatus(
            status="ready" if checks["worker_process"] else "unavailable"
        )
        for name in ("translation", "generation"):
            components[name] = ComponentStatus(
                status="ready" if settings.llm_configured else "unavailable"
            )
    search_ready = local_ready and postgres and qdrant
    return SystemStatus(
        request_id=request_id,
        status="ready" if all(checks.values()) else "unavailable",
        components=components,
        scope="local_retrieval"
        if settings.app_mode == "production"
        else "bootstrap_infrastructure",
        stage="local_retrieval" if settings.app_mode == "production" else "T01",
        capabilities=Capabilities(
            llm_configured=settings.llm_configured,
            search_he=search_ready,
            translation=search_ready and settings.llm_configured,
            answer_generation=search_ready and settings.llm_configured,
            topic_comparison=search_ready and settings.llm_configured,
        ),
    )
