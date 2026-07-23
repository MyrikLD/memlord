from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.dao import MemoryDao
from memlord.models import Memory, Tag
from memlord.schemas import MemoryType
from memlord.search import hybrid_search
from memlord.utils.dt import as_naive_utc, utcnow


def test_as_naive_utc_converts_aware_to_naive_utc():
    aware = datetime(2026, 6, 10, 14, 30, tzinfo=timezone(timedelta(hours=3)))  # 14:30+03:00
    result = as_naive_utc(aware)
    assert result == datetime(2026, 6, 10, 11, 30)  # 11:30 UTC, naive
    assert result.tzinfo is None


def test_as_naive_utc_passes_through_none_and_naive():
    assert as_naive_utc(None) is None
    naive = datetime(2026, 6, 10, 11, 30)
    assert as_naive_utc(naive) == naive


async def _create(
    s: AsyncSession,
    uid: int,
    ws: int,
    content: str,
    name: str,
    *,
    expires_at=None,
    tags: set[str] | None = None,
    force: bool = True,
) -> int:
    mid, _ = await MemoryDao(s, uid).create(
        content=content,
        memory_type=MemoryType.fact,
        metadata={},
        tags=set(tags or set()),
        name=name,
        workspace_id=ws,
        force=force,
        expires_at=expires_at,
    )
    return mid


async def test_get_returns_expired(session, user_id, workspace_id):
    dao = MemoryDao(session, user_id)
    past = utcnow() - timedelta(days=1)
    future = utcnow() + timedelta(days=1)
    await _create(session, user_id, workspace_id, "expired note", "expired", expires_at=past)
    await _create(session, user_id, workspace_id, "active note", "active", expires_at=future)

    expired = await dao.get(name="expired", workspace_id=workspace_id)
    assert expired is not None
    assert expired.expires_at is not None
    assert expired.expires_at <= utcnow()
    active = await dao.get(name="active", workspace_id=workspace_id)
    assert active is not None
    assert active.expires_at is not None


async def test_search_hides_expired(session, user_id, workspace_id):
    past = utcnow() - timedelta(days=1)
    await _create(session, user_id, workspace_id, "Python is a language", "py", expires_at=past)
    await _create(session, user_id, workspace_id, "SQLite is a database", "sq")

    results = await hybrid_search(
        session, "Python", workspace_ids=[workspace_id], similarity_threshold=0.0
    )
    names = {r.name for r in results}
    assert "py" not in names
    assert "sq" in names


async def test_expired_does_not_block_near_duplicate(session, user_id, workspace_id):
    past = utcnow() - timedelta(days=1)
    await _create(
        session,
        user_id,
        workspace_id,
        "The deploy freeze starts on Friday morning",
        "a",
        expires_at=past,
    )
    # A near-identical active memory must be storable — the expired one is ignored
    # by the near-duplicate check (which would otherwise raise without force=True).
    _, created = await MemoryDao(session, user_id).create(
        content="The deploy freeze starts on Friday morning!",
        memory_type=MemoryType.fact,
        metadata={},
        tags=set(),
        name="b",
        workspace_id=workspace_id,
        force=False,
    )
    assert created is True


async def test_purge_expired_removes_only_expired(session, user_id, workspace_id):
    dao = MemoryDao(session, user_id)
    past = utcnow() - timedelta(days=1)
    future = utcnow() + timedelta(days=1)
    await _create(
        session, user_id, workspace_id, "expired one", "expired", expires_at=past, tags={"gone"}
    )
    await _create(session, user_id, workspace_id, "future one", "future", expires_at=future)
    await _create(session, user_id, workspace_id, "forever one", "forever")

    removed = await dao.purge_expired()
    assert removed == 1

    remaining = (await session.execute(select(Memory.name))).scalars().all()
    assert set(remaining) == {"future", "forever"}

    # the expired memory's sole tag is cleaned up as an orphan
    assert await session.scalar(select(Tag.id).where(Tag.name == "gone")) is None


async def test_update_clears_expiry(session, user_id, workspace_id):
    future = utcnow() + timedelta(days=1)
    mid = await _create(session, user_id, workspace_id, "temp fact", "temp", expires_at=future)

    # Clearing expiry (back to never-expires) is the DAO/API path: pass expires_at=None.
    await MemoryDao(session, user_id).update(id=mid, workspace_id=workspace_id, expires_at=None)

    item = await MemoryDao(session, user_id).get(name="temp", workspace_id=workspace_id)
    assert item is not None
    assert item.expires_at is None
