"""created_at must be serialized as timezone-aware ISO 8601 in all MCP tool responses."""

from datetime import datetime

from memlord.schemas import MemoryType


def _assert_tz_aware(created_at: datetime) -> None:
    assert (
        created_at.tzinfo is not None
    ), f"created_at must be timezone-aware: {created_at!r}"


async def test_recall_memory_created_at_has_timezone(mcp_client):
    await mcp_client.call_tool(
        "store_memory",
        {"content": "tz test memory", "memory_type": MemoryType.fact},
    )

    r = await mcp_client.call_tool("recall_memory", {"query": "tz test memory"})
    assert r.data.items, "expected at least one recall result"
    for item in r.data.items:
        _assert_tz_aware(item.created_at)


async def test_list_memories_created_at_has_timezone(mcp_client):
    await mcp_client.call_tool(
        "store_memory",
        {"content": "tz list test memory", "memory_type": MemoryType.fact},
    )

    r = await mcp_client.call_tool("list_memories", {})
    for item in r.data.items:
        _assert_tz_aware(item.created_at)


async def test_search_by_tag_created_at_has_timezone(mcp_client):
    await mcp_client.call_tool(
        "store_memory",
        {
            "content": "tz tag test memory",
            "memory_type": MemoryType.fact,
            "tags": ["tz-test"],
        },
    )

    r = await mcp_client.call_tool(
        "search_by_tag",
        {"tags": ["tz-test"], "operation": "AND"},
    )
    assert r.data.items, "expected at least one result"
    for item in r.data.items:
        _assert_tz_aware(item.created_at)
