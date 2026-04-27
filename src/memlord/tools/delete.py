from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas.tools import DeleteResult

mcp = FastMCP()


@mcp.tool(
    output_schema=DeleteResult.model_json_schema(),
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
)
async def delete_memory(
    name: str,
    workspace: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> DeleteResult:
    """Delete a memory by name. Pass workspace to disambiguate if the name exists in multiple workspaces."""
    ws_id: int | None = None
    if workspace is not None:
        ws = await WorkspaceDao(s, uid).get_by_name(workspace)
        if ws is None:
            raise ValueError(f"Workspace {workspace!r} not found")
        ws_id = ws.id
    dao = MemoryDao(s, uid)
    item = await dao.get(name=name, workspace_id=ws_id)
    if item is None:
        raise ValueError(f"Memory with name={name!r} not found")
    await dao.delete(item.id, item.workspace_id)
    return DeleteResult(success=True, name=name)
