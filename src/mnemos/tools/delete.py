from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.auth import UserDep
from mnemos.dao import MemoryDao
from mnemos.dao.workspace import WorkspaceDao
from mnemos.db import MCPSessionDep
from mnemos.schemas import DeleteResult

mcp = FastMCP()


@mcp.tool(
    output_schema=DeleteResult.model_json_schema(),
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
)
async def delete_memory(
    id: int,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = UserDep,  # type: ignore[assignment]
) -> DeleteResult:
    """Delete a memory by ID. Removes from vec index and FTS (via trigger)."""
    workspace_ids = await WorkspaceDao(s).get_accessible_workspace_ids(uid)
    dao = MemoryDao(s)
    await dao.delete(id, uid, workspace_ids=workspace_ids)
    return DeleteResult(success=True, id=id)
