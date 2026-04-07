"""Full MCP tool pipeline: store → get → update → search → delete."""

import pytest
from fastmcp.exceptions import ToolError

from memlord.schemas import MemoryType


async def test_pipeline(mcp_client):
    # --- store ---
    r = await mcp_client.call_tool(
        "store_memory",
        {
            "content": "pipeline test memory",
            "memory_type": MemoryType.fact,
            "tags": ["pipeline", "test"],
            "name": "pipeline-test",
        },
    )
    assert r.data.created is True
    mid = r.data.name

    # --- get ---
    r = await mcp_client.call_tool("get_memory", {"name": mid})
    assert r.data.content == "pipeline test memory"
    assert r.data.memory_type == MemoryType.fact
    assert sorted(r.data.tags) == ["pipeline", "test"]

    # --- update ---
    r = await mcp_client.call_tool(
        "update_memory",
        {
            "name": mid,
            "memory_type": MemoryType.fact,
            "content": "updated pipeline memory",
            "tags": ["pipeline", "updated"],
        },
    )
    assert r.data.name == mid

    r = await mcp_client.call_tool("get_memory", {"name": mid})
    assert r.data.content == "updated pipeline memory"
    assert sorted(r.data.tags) == ["pipeline", "updated"]

    # --- retrieve ---
    r = await mcp_client.call_tool(
        "retrieve_memory",
        {"query": "updated pipeline memory", "limit": 10},
    )
    names = [m.name for m in r.data]
    assert mid in names

    # --- list_memories ---
    r = await mcp_client.call_tool("list_memories", {"page": 1, "page_size": 50})
    names = [m.name for m in r.data.items]
    assert mid in names

    # --- search by tag ---
    r = await mcp_client.call_tool(
        "search_by_tag", {"tags": ["pipeline", "updated"], "operation": "AND"}
    )
    ids = [m.name for m in r.data.items]
    assert mid in ids

    # --- delete ---
    await mcp_client.call_tool("delete_memory", {"name": mid})

    with pytest.raises(ToolError):
        await mcp_client.call_tool("get_memory", {"name": mid})
