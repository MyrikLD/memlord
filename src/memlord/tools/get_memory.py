from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas import MemoryDetail

mcp = FastMCP()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def get_memory(
    name: str,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> MemoryDetail:
    """Fetch full content of a memory by name."""
    item = await MemoryDao(s, uid).get(name=name)
    if item is None:
        raise ValueError(f"Memory with name={name!r} not found")

    ws_name: str | None = None
    if item.workspace_id is not None:
        names = await WorkspaceDao(s).get_names_by_ids({item.workspace_id})
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
