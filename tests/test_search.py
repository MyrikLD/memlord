from datetime import datetime, timedelta, timezone

from dateparser.search import search_dates
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.dao import MemoryDao
from mnemos.models import Memory
from mnemos.schemas import MemoryType
from mnemos.search import hybrid_search


async def _store(s: AsyncSession, content: str, uid: int) -> int:
    mid, _ = await MemoryDao(s).create(
        content=content,
        memory_type=MemoryType.fact,
        metadata={},
        tags=[],
        user_id=uid,
    )
    return mid


async def test_empty_db(session, user_id):
    results = await hybrid_search(
        session, "anything", user_id=user_id, similarity_threshold=0.0
    )
    assert results == []


async def test_bm25_match(session, user_id):
    await _store(session, "Python is a programming language", user_id)
    await _store(session, "SQLite is a database engine", user_id)

    results = await hybrid_search(
        session, "Python programming", user_id=user_id, similarity_threshold=0.0
    )
    assert any("Python" in r.content for r in results)


async def test_vector_semantic_match(session, user_id):
    await _store(session, "I love cats and kittens", user_id)
    await _store(session, "SQL database with indexes", user_id)

    results = await hybrid_search(
        session, "feline animals", user_id=user_id, similarity_threshold=0.0
    )
    assert any("cats" in r.content for r in results)


async def test_threshold_zero_includes_bm25_hit(session, user_id):
    """Regression: threshold=0.0 must not filter BM25-only matches."""
    await _store(session, "The quick brown fox jumps over the lazy dog", user_id)

    results = await hybrid_search(
        session, "quick brown fox", user_id=user_id, similarity_threshold=0.0
    )
    assert results


async def test_high_threshold_filters_unrelated(session, user_id):
    await _store(session, "Python is a programming language", user_id)

    results = await hybrid_search(
        session,
        "quantum physics experiment",
        user_id=user_id,
        similarity_threshold=0.95,
    )
    assert results == []


async def test_limit(session, user_id):
    for i in range(5):
        await _store(session, f"memory about topic number {i}", user_id)

    results = await hybrid_search(
        session, "memory topic", user_id=user_id, limit=2, similarity_threshold=0.0
    )
    assert len(results) <= 2


async def test_date_filter_today(session, user_id):
    mid = await _store(session, "something stored today", user_id)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
    await session.execute(
        update(Memory).where(Memory.id == mid).values(created_at=yesterday)
    )
    mid2 = await _store(session, "something stored recently", user_id)

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )
    results = await hybrid_search(
        session,
        "something",
        user_id=user_id,
        similarity_threshold=0.0,
        date_from=today_start,
    )
    ids = [r.id for r in results]
    assert mid2 in ids
    assert mid not in ids


async def test_date_filter_includes_today(session, user_id):
    """Regression: date_from = start-of-day must include memories created today."""
    mid = await _store(session, "python programming language tutorial", user_id)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    date_to = now + timedelta(seconds=5)

    results = await hybrid_search(
        session,
        "python programming",
        user_id=user_id,
        similarity_threshold=0.0,
        date_from=today_midnight,
        date_to=date_to,
    )
    assert any(r.id == mid for r in results)


async def test_tag_search(session, user_id):
    dao = MemoryDao(session)
    await dao.create(
        "Zigbee migration plan",
        MemoryType.fact,
        {},
        ["matter", "zigbee2mqtt"],
        user_id=user_id,
    )
    results = await hybrid_search(
        session, "matter", user_id=user_id, similarity_threshold=0.0
    )
    assert results


def test_dateparser_today_truncates_before_now():
    """dateparser 'today' truncated to midnight must be before current time."""
    found = search_dates(
        "today",
        settings={"PREFER_DATES_FROM": "past", "RETURN_AS_TIMEZONE_AWARE": False},
    )
    assert found
    truncated = found[0][1].replace(hour=0, minute=0, second=0, microsecond=0)
    assert truncated <= datetime.now()
    assert truncated.hour == 0 and truncated.minute == 0 and truncated.second == 0
