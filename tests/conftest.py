import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import insert, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from mnemos.auth import hash_password
from mnemos.config import settings
from mnemos.models.base import Base
from mnemos.models.user import User


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


@pytest_asyncio.fixture
async def session(test_db_url):
    engine = create_async_engine(test_db_url)
    async with engine.connect() as conn:
        async with AsyncSession(bind=conn, expire_on_commit=False) as s:
            yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def user_id(session: AsyncSession) -> int:
    """Create a test user and return its id."""
    uid = await session.scalar(
        insert(User)
        .values(
            email="test@example.com",
            display_name="Test User",
            hashed_password=hash_password("test-password"),
        )
        .returning(User.id)
    )
    assert uid is not None
    await session.flush()
    return uid
