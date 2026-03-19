from fastmcp import FastMCP
from memlord.config import settings
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
    auth=MemlordOAuthProvider(
        base_url=settings.base_url,
        jwt_secret=settings.oauth_jwt_secret,
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
