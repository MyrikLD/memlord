from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.access import Principal
from memlord.auth import MCPUserDep
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas import WorkspaceInfo

mcp = FastMCP()


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
async def list_workspaces(
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: Principal = MCPUserDep,  # type: ignore[assignment]
) -> list[WorkspaceInfo]:
    """List all workspaces you are a member of (personal + shared)."""
    return await WorkspaceDao(s, uid).list_workspaces()
