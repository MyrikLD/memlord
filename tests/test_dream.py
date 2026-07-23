from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from memlord.dao import MemoryDao
from memlord.schemas import MemoryType
from memlord.utils.dt import utcnow


async def _store(
    s: AsyncSession,
    content: str,
    uid: int,
    workspace_id: int,
    expires_at=None,
) -> int:
    mid, _ = await MemoryDao(s, uid).create(
        content=content,
        memory_type=MemoryType.fact,
        metadata={},
        tags=set(),
        name=content[:60].strip(),
        workspace_id=workspace_id,
        force=True,
        expires_at=expires_at,
    )
    return mid


async def test_similar_pairs_finds_near_duplicates(session, user_id, workspace_id):
    await _store(session, "The deploy pipeline runs on GitHub Actions", user_id, workspace_id)
    await _store(
        session, "Deployment pipeline is executed via GitHub Actions", user_id, workspace_id
    )
    await _store(session, "My cat is named Barsik and likes tuna", user_id, workspace_id)

    pairs = await MemoryDao(session, user_id).similar_pairs(similarity_threshold=0.6)

    assert len(pairs) == 1
    names = {pairs[0]["name_a"], pairs[0]["name_b"]}
    assert names == {
        "The deploy pipeline runs on GitHub Actions",
        "Deployment pipeline is executed via GitHub Actions",
    }
    assert pairs[0]["similarity"] >= 0.6


async def test_similar_pairs_excludes_expired(session, user_id, workspace_id):
    past = utcnow() - timedelta(days=1)
    await _store(session, "The deploy pipeline runs on GitHub Actions", user_id, workspace_id)
    await _store(
        session,
        "Deployment pipeline is executed via GitHub Actions",
        user_id,
        workspace_id,
        expires_at=past,
    )

    pairs = await MemoryDao(session, user_id).similar_pairs(similarity_threshold=0.6)
    assert pairs == []


async def test_expiry_report_splits_expired_and_soon(session, user_id, workspace_id):
    await _store(
        session,
        "Old temporary note",
        user_id,
        workspace_id,
        expires_at=utcnow() - timedelta(days=1),
    )
    await _store(
        session,
        "Fresh temporary note",
        user_id,
        workspace_id,
        expires_at=utcnow() + timedelta(days=3),
    )
    await _store(
        session, "Far future note", user_id, workspace_id, expires_at=utcnow() + timedelta(days=90)
    )
    await _store(session, "Permanent note", user_id, workspace_id)

    expired, soon = await MemoryDao(session, user_id).expiry_report()

    assert [e["name"] for e in expired] == ["Old temporary note"]
    assert [e["name"] for e in soon] == ["Fresh temporary note"]


async def test_dream_report_tool(mcp_client, session, user_id, workspace_id):
    await _store(session, "Project uses PostgreSQL with pgvector extension", user_id, workspace_id)
    await _store(session, "The project database is PostgreSQL plus pgvector", user_id, workspace_id)

    r = await mcp_client.call_tool("dream_report", {"similarity_threshold": 0.6})

    pairs = r.data.similar_pairs
    assert len(pairs) == 1
    assert pairs[0].workspace is not None
    assert r.data.expired == []
    assert r.data.expiring_soon == []


async def test_dream_prompt_registered(mcp_client):
    prompts = await mcp_client.list_prompts()
    assert "dream" in {p.name for p in prompts}
