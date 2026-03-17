from datetime import datetime, timedelta, timezone

from dateparser.search import search_dates
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.dao import MemoryDao
from mnemos.models import Memory
from mnemos.schemas import MemoryType
from mnemos.search import hybrid_search


async def _store(s: AsyncSession, content: str) -> int:
    mid, new = await MemoryDao(s).create(
        content=content,
        memory_type=MemoryType.fact,
        metadata={},
        tags=[],
    )
    return mid


async def test_empty_db(session):
    results = await hybrid_search(session, "anything", similarity_threshold=0.0)
    assert results == []


async def test_bm25_match(session):
    await _store(session, "Python is a programming language")
    await _store(session, "SQLite is a database engine")

    results = await hybrid_search(
        session, "Python programming", similarity_threshold=0.0
    )
    assert any("Python" in r.content for r in results)


async def test_vector_semantic_match(session):
    await _store(session, "I love cats and kittens")
    await _store(session, "SQL database with indexes")

    results = await hybrid_search(session, "feline animals", similarity_threshold=0.0)
    assert any("cats" in r.content for r in results)


async def test_threshold_zero_includes_bm25_hit(session):
    """Regression: threshold=0.0 must not filter BM25-only matches."""
    await _store(session, "The quick brown fox jumps over the lazy dog")

    results = await hybrid_search(session, "quick brown fox", similarity_threshold=0.0)
    assert results


async def test_high_threshold_filters_unrelated(session):
    await _store(session, "Python is a programming language")

    results = await hybrid_search(
        session, "quantum physics experiment", similarity_threshold=0.95
    )
    assert results == []


async def test_limit(session):
    for i in range(5):
        await _store(session, f"memory about topic number {i}")

    results = await hybrid_search(
        session, "memory topic", limit=2, similarity_threshold=0.0
    )
    assert len(results) <= 2


async def test_date_filter_today(session):
    mid = await _store(session, "something stored today")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
    await session.execute(
        update(Memory).where(Memory.id == mid).values(created_at=yesterday)
    )
    mid2 = await _store(session, "something stored recently")

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )
    results = await hybrid_search(
        session,
        "something",
        similarity_threshold=0.0,
        date_from=today_start,
    )
    ids = [r.id for r in results]
    assert mid2 in ids
    assert mid not in ids


async def test_date_filter_includes_today(session):
    """Regression: date_from = start-of-day must include memories created today."""
    mid = await _store(session, "python programming language tutorial")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    date_to = now + timedelta(seconds=5)

    results = await hybrid_search(
        session,
        "python programming",
        similarity_threshold=0.0,
        date_from=today_midnight,
        date_to=date_to,
    )
    assert any(r.id == mid for r in results)


async def test_tag_search(session):
    dao = MemoryDao(session)
    await dao.create(
        "Zigbee migration plan", MemoryType.fact, {}, ["matter", "zigbee2mqtt"]
    )
    results = await hybrid_search(session, "matter", similarity_threshold=0.0)
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
