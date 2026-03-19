from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import UserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas import MemoryType, StoreResult

mcp = FastMCP()


@mcp.tool(
    output_schema=StoreResult.model_json_schema(),
    annotations=ToolAnnotations(idempotentHint=True, destructiveHint=False),
)
async def store_memory(
    content: str,
    memory_type: MemoryType,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    workspace: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = UserDep,  # type: ignore[assignment]
) -> StoreResult:
    """Save a new memory. Idempotent: returns existing if content already stored.

    workspace: name of the workspace to store into (must be a member).
               Omit or pass None to store as a personal memory.
    """
    ws_dao = WorkspaceDao(s)
    if workspace is not None:
        ws = await ws_dao.get_by_name(workspace, uid)
        if ws is None:
            raise ValueError(
                f"Workspace '{workspace}' not found or you are not a member. "
                "Use list_workspaces() to see available workspaces."
            )
        if not await ws_dao.can_write(ws.id, uid):
            raise ValueError(f"You don't have write access to workspace '{workspace}'.")
    else:
        ws = await ws_dao.get_personal(uid)
    workspace_id = ws.id

    dao = MemoryDao(s, uid)
    memory_id, created = await dao.create(
        content=content,
        memory_type=memory_type,
        metadata=metadata or {},
        tags=tags or [],
        workspace_id=workspace_id,
    )
    return StoreResult(id=memory_id, created=created)
