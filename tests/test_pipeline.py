"""Full MCP tool pipeline: list_workspaces → store → get → update → search → move → delete."""

import pytest
from fastmcp.exceptions import ToolError

from memlord.dao.workspace import WorkspaceDao
from memlord.schemas import MemoryType


async def test_pipeline(mcp_client, session, user_id):
    # --- list_workspaces (a fresh user has exactly one personal workspace) ---
    r = await mcp_client.call_tool("list_workspaces", {})
    personal = [w for w in r.data if w.is_personal]
    assert len(personal) == 1
    personal_ws = personal[0].name

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

    # --- move to another workspace ---
    target_ws = await WorkspaceDao(session, user_id).create(name="pipeline-target")
    r = await mcp_client.call_tool(
        "move_memory",
        {"name": mid, "to_workspace": target_ws.name, "from_workspace": personal_ws},
    )
    assert r.data.name == mid

    # gone from the personal workspace, present in the target
    with pytest.raises(ToolError):
        await mcp_client.call_tool("get_memory", {"name": mid, "workspace": personal_ws})

    r = await mcp_client.call_tool("get_memory", {"name": mid, "workspace": target_ws.name})
    assert r.data.content == "updated pipeline memory"
    assert r.data.workspace == target_ws.name

    # --- delete (from the target workspace) ---
    await mcp_client.call_tool("delete_memory", {"name": mid, "workspace": target_ws.name})

    with pytest.raises(ToolError):
        await mcp_client.call_tool("get_memory", {"name": mid, "workspace": target_ws.name})
