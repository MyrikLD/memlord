from contextlib import asynccontextmanager

import sqlite_vec  # type: ignore[import-untyped]
from mnemos.config import settings
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            f"sqlite+aiosqlite:///{settings.db_path}",
            echo=False,
        )

        @event.listens_for(_engine.sync_engine, "connect")
        def on_connect(dbapi_conn, _):  # noqa: ANN001
            dbapi_conn.enable_load_extension(True)
            sqlite_vec.load(dbapi_conn)
            dbapi_conn.enable_load_extension(False)

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=True)
    return _session_factory


@asynccontextmanager
async def session():
    async with get_session_factory()() as s:
        yield s


async def session_dep():
    async with get_session_factory()() as s:
        yield s


SessionDep = Annotated[AsyncSession, Depends(session_dep)]

__all__ = ["session", "SessionDep"]
