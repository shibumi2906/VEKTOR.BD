import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import Settings


def migrate(connection):
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run():
    url = Settings().postgres_url.get_secret_value()
    if not url:
        raise ValueError("POSTGRES_URL is required")
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


asyncio.run(run())
