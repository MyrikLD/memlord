"""Full MCP tool pipeline: store → get → update → search → delete."""

import pytest

from memlord.schemas import MemoryType


async def test_pipeline(mcp_client):
    # --- store ---
    r = await mcp_client.call_tool(
        "store_memory",
        {
            "content": "pipeline test memory",
            "memory_type": MemoryType.fact,
            "tags": ["pipeline", "test"],
        },
    )
    assert r.data.created is True
    mid = r.data.id

    # --- get ---
    r = await mcp_client.call_tool("get_memory", {"id": mid})
    assert r.data.content == "pipeline test memory"
    assert r.data.memory_type == MemoryType.fact
    assert sorted(r.data.tags) == ["pipeline", "test"]

    # --- update ---
    r = await mcp_client.call_tool(
        "update_memory",
        {
            "id": mid,
            "memory_type": MemoryType.fact,
            "content": "updated pipeline memory",
            "tags": ["pipeline", "updated"],
        },
    )
    assert r.data.id == mid

    r = await mcp_client.call_tool("get_memory", {"id": mid})
    assert r.data.content == "updated pipeline memory"
    assert sorted(r.data.tags) == ["pipeline", "updated"]

    # --- search by tag ---
    r = await mcp_client.call_tool(
        "search_by_tag", {"tags": ["pipeline", "updated"], "operation": "AND"}
    )
    ids = [m.id for m in r.data.items]
    assert mid in ids

    # --- delete ---
    await mcp_client.call_tool("delete_memory", {"id": mid})

    with pytest.raises(Exception):
        await mcp_client.call_tool("get_memory", {"id": mid})
