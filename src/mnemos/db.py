from contextlib import asynccontextmanager
from functools import cache
from typing import Annotated

import sqlite_vec
from fastapi import Depends as APIDepends
from fastmcp.dependencies import Depends as MCPDepends
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from mnemos.config import settings


@cache
def get_engine() -> AsyncEngine:
    _engine = create_async_engine(
        f"sqlite+aiosqlite:///{settings.db_path}",
        echo=False,
    )

    @event.listens_for(_engine.sync_engine, "connect")
    def on_connect(dbapi_conn, _):  # noqa: ANN001
        # aiosqlite wraps the raw sqlite3 connection;
        # driver_connection is aiosqlite.Connection, ._conn is sqlite3.Connection
        raw = getattr(dbapi_conn, "driver_connection", dbapi_conn)
        raw = getattr(raw, "_conn", raw)
        raw.enable_load_extension(True)
        sqlite_vec.load(raw)
        raw.enable_load_extension(False)

    return _engine


@cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=True)


async def session_dep():
    session_factory = get_session_factory()
    async with session_factory() as s, s.begin():
        yield s


MCPSessionDep = MCPDepends(asynccontextmanager(session_dep))
# APISessionDep = APIDepends(session_dep)
APISessionDep = Annotated[AsyncSession, APIDepends(session_dep)]

session = asynccontextmanager(session_dep)

__all__ = ["MCPSessionDep", "APISessionDep", "session"]
