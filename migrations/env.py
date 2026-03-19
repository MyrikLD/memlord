import asyncio
from logging.config import fileConfig

from alembic import context
from memlord.config import settings
from memlord.models import Memory, MemoryTag, OAuthClient, SchemaVersion, Tag  # noqa: F401
from memlord.models.base import Base
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.db_url)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda connection: context.configure(
                connection=connection,
                target_metadata=target_metadata,
            )
        )
        await conn.run_sync(lambda _: context.run_migrations())
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
