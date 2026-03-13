import pytest_asyncio
import sqlite_vec
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from mnemos.models import (
    Memory,
    MemoryTag,
    Tag,
)  # noqa: F401 — registers tables with Base
from mnemos.models.base import Base


async def _load_sqlite_vec(async_conn) -> None:
    """Load sqlite-vec in aiosqlite's worker thread where the sqlite3 connection lives."""
    aio = (
        async_conn.sync_connection.connection.driver_connection
    )  # aiosqlite.Connection
    await aio._execute(aio._conn.enable_load_extension, True)
    await aio._execute(sqlite_vec.load, aio._conn)
    await aio._execute(aio._conn.enable_load_extension, False)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await _load_sqlite_vec(conn)

        await conn.run_sync(Base.metadata.create_all)
        for stmt in [
            "CREATE VIRTUAL TABLE memories_fts USING fts5(content, memory_id UNINDEXED, tokenize='porter unicode61')",
            "CREATE VIRTUAL TABLE memories_vec USING vec0(memory_id INTEGER PRIMARY KEY, embedding FLOAT[384])",
            "CREATE TRIGGER memories_fts_ai AFTER INSERT ON memories BEGIN "
            "INSERT INTO memories_fts(memory_id, content) VALUES (new.id, new.content); END",
        ]:
            await conn.execute(text(stmt))

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s, s.begin():
        yield s

    await engine.dispose()
