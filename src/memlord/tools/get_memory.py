from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas.tools import MemoryDetail

mcp = FastMCP()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def get_memory(
    name: str,
    workspace: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> MemoryDetail:
    """Fetch full content of a single memory by numeric ID.

    Use only when you already know the ID — e.g. after retrieve_memory() or recall_memory()
    which return IDs in their results alongside compact snippets.
    Do NOT use for search — use retrieve_memory() for semantic/text search
    or recall_memory() for time-based queries like 'last week'.
    """
    ws_dao = WorkspaceDao(s, uid)
    ws_id: int | None = None
    if workspace is not None:
        ws = await ws_dao.get_by_name(workspace)
        if ws is None:
            raise ValueError(f"Workspace {workspace!r} not found")
        ws_id = ws.id
    item = await MemoryDao(s, uid).get(name=name, workspace_id=ws_id)
    if item is None:
        raise ValueError(f"Memory with name={name!r} not found")

    names = await ws_dao.get_names_by_ids({item.workspace_id})
    ws_name = names.get(item.workspace_id)

    return MemoryDetail(
        name=item.name,
        content=item.content,
        memory_type=item.memory_type,
        metadata=item.metadata,
        tags=item.tags,
        created_at=item.created_at,
        workspace=ws_name,
    )
