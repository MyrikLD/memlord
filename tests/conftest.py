import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastmcp import Client
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from memlord.auth import MCPUserDep, hash_password
from memlord.config import settings
from memlord.dao.user import UserDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep, session_dep
from memlord.main import app
from memlord.models import Base
from memlord.server import mcp
from memlord.ui.utils import make_session_token


@pytest.fixture(scope="session")
def test_db_url(worker_id):
    url = make_url(settings.db_url)
    root_url = url.set(database=None)
    test_db_name = f"test_{worker_id}"

    async def setup():
        root_engine = create_async_engine(root_url)
        async with root_engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text(f"DROP DATABASE IF EXISTS {test_db_name}"))
            await conn.execute(text(f"CREATE DATABASE {test_db_name}"))
        await root_engine.dispose()

        engine = create_async_engine(url.set(database=test_db_name))
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(setup())
    yield url.set(database=test_db_name)

    async def cleanup():
        root_engine = create_async_engine(root_url)
        async with root_engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text(f"DROP DATABASE IF EXISTS {test_db_name}"))
        await root_engine.dispose()

    try:
        asyncio.run(cleanup())
    except Exception as e:
        print(f"Warning: failed to drop test database: {e}")


@pytest.fixture
async def session(test_db_url):
    engine = create_async_engine(test_db_url)
    async with engine.connect() as conn:
        async with AsyncSession(bind=conn, expire_on_commit=False) as s:
            yield s
    await engine.dispose()


@pytest.fixture
async def user_id(session: AsyncSession) -> int:
    """Create a test user (with personal workspace) and return its id."""
    user = await UserDao(session).create(
        email="test@example.com",
        display_name="Test User",
        hashed_password=hash_password("test-password"),
    )
    return user.id  # type: ignore[return-value]


@pytest.fixture
async def workspace_id(session: AsyncSession, user_id: int) -> int:
    """Return the personal workspace id for the test user."""
    ws = await WorkspaceDao(session, user_id).get_personal()
    return ws.id


@pytest.fixture
async def mcp_client(session, user_id):
    async def _session():
        yield session

    async def _user():
        yield user_id

    with (
        patch.object(MCPSessionDep, "factory", asynccontextmanager(_session)),
        patch.object(MCPUserDep, "factory", asynccontextmanager(_user)),
    ):
        async with Client(mcp) as client:
            yield client


@pytest.fixture
async def api_client(session, user_id):
    async def _override_session():
        yield session

    app.dependency_overrides[session_dep] = _override_session
    cookie = make_session_token(user_id)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        client.cookies.set("memlord_session", cookie)
        yield client
    app.dependency_overrides.pop(session_dep, None)
