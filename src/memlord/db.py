from contextlib import asynccontextmanager
from functools import cache
from typing import Annotated

from fastapi import Depends as APIDepends
from fastmcp.dependencies import Depends as MCPDepends
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from memlord.config import settings


@cache
def get_engine() -> AsyncEngine:
    return create_async_engine(settings.db_url, echo=settings.db_echo, pool_pre_ping=True)


@cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=True)


async def session_dep():
    session_factory = get_session_factory()
    async with session_factory() as s, s.begin():
        yield s


session = asynccontextmanager(session_dep)
MCPSessionDep = MCPDepends(session)
APISessionDep = Annotated[AsyncSession, APIDepends(session_dep, scope="function")]


__all__ = ["MCPSessionDep", "APISessionDep", "session"]
