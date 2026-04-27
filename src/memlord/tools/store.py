from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas import MemoryType
from memlord.schemas.tools import StoreResult

mcp = FastMCP()


@mcp.tool(
    output_schema=StoreResult.model_json_schema(),
    annotations=ToolAnnotations(idempotentHint=True, destructiveHint=False),
)
async def store_memory(
    content: str,
    memory_type: MemoryType,
    name: str,
    tags: set[str] | None = None,
    metadata: dict | None = None,
    workspace: str | None = Field(
        None,
        description="Name of the workspace to store into (must be a member). Omit or pass None to store as a personal memory.",
    ),
    force: bool = Field(False, description="Skip near-duplicate check and store unconditionally."),
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> StoreResult:
    """Save a new memory. Idempotent: returns existing if content already stored.

    name: human-readable name, unique within the workspace.
    workspace: name of the workspace to store into. Omit to store as a personal memory.
    force: skip near-duplicate check and store unconditionally.
    """
    ws_dao = WorkspaceDao(s, uid)
    if workspace is not None:
        ws = await ws_dao.get_by_name(workspace)
        if ws is None:
            raise ValueError(
                f"Workspace '{workspace}' not found or you are not a member. "
                "Use list_workspaces() to see available workspaces."
            )
        if not await ws_dao.can_write(ws.id):
            raise ValueError(f"You don't have write access to workspace '{workspace}'.")
    else:
        ws = await ws_dao.get_personal()
    workspace_id = ws.id

    dao = MemoryDao(s, uid)
    _, created = await dao.create(
        content=content,
        memory_type=memory_type,
        metadata=metadata or {},
        tags=tags or set(),
        workspace_id=workspace_id,
        force=force,
        name=name,
    )
    return StoreResult(name=name, created=created)
