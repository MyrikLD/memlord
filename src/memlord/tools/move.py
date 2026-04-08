from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.db import MCPSessionDep
from memlord.schemas import StoreResult

mcp = FastMCP()


@mcp.tool(
    output_schema=StoreResult.model_json_schema(),
    annotations=ToolAnnotations(idempotentHint=False, destructiveHint=False),
)
async def move_memory(
    id: int,
    to_workspace: str,
    from_workspace: str | None = None,
    s: AsyncSession = MCPSessionDep,
    uid: int = MCPUserDep,
) -> StoreResult:
    """Move a memory to a different workspace.

    id: memory ID to move.
    workspace: name of the target workspace (must be a member with write access).
    """

    await MemoryDao(s, uid).move_by_name(id, from_workspace, to_workspace)
    return StoreResult(id=id, created=False)
