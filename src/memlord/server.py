from fastmcp import FastMCP

from memlord.config import settings
from memlord.db import session
from memlord.oauth import MemlordOAuthProvider
from memlord.tools import (
    delete,
    get_memory,
    list_memories,
    move,
    recall,
    retrieve,
    search_by_tag,
    store,
    update,
    workspaces,
)

mcp: FastMCP = FastMCP(
    "Memlord",
    instructions=(
        "Use this MCP to persist and retrieve memories across sessions.\n\n"
        "Before storing a memory, call list_workspaces and pick the most relevant workspace "
        "based on context (personal by default). Use store_memory for facts, preferences, "
        "instructions, or feedback worth remembering. At the start of a session call "
        "recall_memory or retrieve_memory to surface relevant context. "
        "Use get_memory(id) only when you need the full content of a specific memory — "
        "search results return snippets to save tokens."
    ),
    auth=MemlordOAuthProvider(
        base_url=settings.base_url,
        jwt_secret=settings.oauth_jwt_secret,
        session_factory=session,
    ),
)

mcp.mount(store)
mcp.mount(retrieve)
mcp.mount(recall)
mcp.mount(get_memory)
mcp.mount(list_memories)
mcp.mount(search_by_tag)
mcp.mount(delete)
mcp.mount(update)
mcp.mount(move)
mcp.mount(workspaces)
