from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.embeddings import embed
from mnemos.models import Memory
from mnemos.search import fts5_escape, hybrid_search


async def _store(s: AsyncSession, content: str) -> int:
    (mid,) = (
        await s.execute(insert(Memory).values(content=content).returning(Memory.id))
    ).one()
    vec = embed(content)
    await s.execute(
        text("INSERT INTO memories_vec(memory_id, embedding) VALUES (:id, :vec)"),
        {"id": mid, "vec": "[" + ",".join(str(v) for v in vec) + "]"},
    )
    return mid


def test_fts5_escape():
    assert fts5_escape("mcp-memory foo") == '"mcp-memory" "foo"'
    assert fts5_escape("hello") == '"hello"'


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
    """Regression: with fixed similarity formula, threshold=0.0 must not filter BM25 matches."""
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
    # Backdate one memory to yesterday
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
        date_from=today_start.isoformat(sep=" "),
    )
    ids = [r.id for r in results]
    assert mid2 in ids
    assert mid not in ids


async def test_date_filter_truncated_to_start_of_day(session):
    """Regression: 'today' must use start-of-day, not current time, as date_from."""

    mid = await _store(session, "recall this memory today")

    # Simulate what recall_memory does with date parsing
    from dateparser.search import search_dates

    found = search_dates(
        "today",
        settings={"PREFER_DATES_FROM": "past", "RETURN_AS_TIMEZONE_AWARE": False},
    )
    assert found
    dt = found[0][1]
    # With truncation fix, start of day — memory created moments ago must be included
    date_from = dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(sep=" ")
    date_to = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")

    results = await hybrid_search(
        session,
        "recall memory",
        similarity_threshold=0.0,
        date_from=date_from,
        date_to=date_to,
    )
    assert any(r.id == mid for r in results)
