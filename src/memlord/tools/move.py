from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas.tools import StoreResult

mcp = FastMCP()


@mcp.tool(
    output_schema=StoreResult.model_json_schema(),
    annotations=ToolAnnotations(idempotentHint=False, destructiveHint=False),
)
async def move_memory(
    name: str,
    to_workspace: str,
    from_workspace: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> StoreResult:
    """Move a memory to a different to_workspace.

    name: name of the memory to move.
    workspace: name of the target workspace (must be a member with write access).
    from_workspace: disambiguate source if the name exists in multiple workspaces.
    """
    ws_dao = WorkspaceDao(s, uid)
    from_ws_id: int | None = None
    if from_workspace is not None:
        from_ws = await ws_dao.get_by_name(from_workspace)
        if from_ws is None:
            raise ValueError(f"Workspace {from_workspace!r} not found")
        from_ws_id = from_ws.id

    if from_ws_id is None:
        from_ws_id = (await ws_dao.get_personal()).id

    dao = MemoryDao(s, uid)
    memory_id = await dao.get_id_by_name(name, workspace_id=from_ws_id)
    if memory_id is None:
        raise ValueError(f"Memory with name={name!r} not found")

    ws = await ws_dao.get_by_name(to_workspace)
    if ws is None:
        raise ValueError(f"Workspace {to_workspace!r} not found")

    await dao.move(memory_id, from_ws_id, ws.id)
    return StoreResult(name=name, created=False)
