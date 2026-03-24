from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.db import MCPSessionDep
from memlord.schemas import MemoryListItem

mcp = FastMCP()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def get_memory(
    id: int,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> MemoryListItem:
    """Fetch a single memory by ID with full details (tags, metadata)."""
    result = await MemoryDao(s, uid).get(id)
    if result is None:
        raise ValueError(f"Memory with id={id} not found")
    return result
