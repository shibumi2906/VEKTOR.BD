import asyncpg


async def connect(settings):
    return await asyncpg.connect(
        settings.postgres_url.get_secret_value().replace(
            "postgresql+asyncpg://", "postgresql://", 1
        ),
        timeout=10,
    )
