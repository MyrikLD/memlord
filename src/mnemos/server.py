from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from mnemos.config import settings
from mnemos.oauth import MnemosOAuthProvider
from mnemos.tools import (
    delete,
    health,
    list_memories,
    recall,
    retrieve,
    search_by_tag,
    store,
)


def _build_auth() -> AuthProvider | None:
    if settings.oauth_jwt_secret and settings.oauth_password and settings.base_url:
        return MnemosOAuthProvider(
            base_url=settings.base_url,
            jwt_secret=settings.oauth_jwt_secret,
            password=settings.oauth_password,
        )
    return None


mcp: FastMCP = FastMCP("Mnemos", auth=_build_auth())

mcp.mount(store)
mcp.mount(retrieve)
mcp.mount(recall)
mcp.mount(list_memories)
mcp.mount(search_by_tag)
mcp.mount(delete)
mcp.mount(health)
