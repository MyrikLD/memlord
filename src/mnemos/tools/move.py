from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.auth import UserDep
from mnemos.dao import MemoryDao
from mnemos.dao.workspace import WorkspaceDao
from mnemos.db import MCPSessionDep
from mnemos.schemas import StoreResult

mcp = FastMCP()


@mcp.tool(
    output_schema=StoreResult.model_json_schema(),
    annotations=ToolAnnotations(idempotentHint=False, destructiveHint=False),
)
async def move_memory(
    id: int,
    workspace: str,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = UserDep,  # type: ignore[assignment]
) -> StoreResult:
    """Move a memory to a different workspace.

    id: memory ID to move.
    workspace: name of the target workspace (must be a member with write access).
    """
    ws = await WorkspaceDao(s).get_by_name(workspace, uid)
    if ws is None:
        raise ValueError(
            f"Workspace '{workspace}' not found or you are not a member. "
            "Use list_workspaces() to see available workspaces."
        )

    await MemoryDao(s, uid).move(id, ws.id)
    return StoreResult(id=id, created=False)
