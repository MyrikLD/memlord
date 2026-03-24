from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.db import MCPSessionDep
from memlord.schemas import DeleteResult

mcp = FastMCP()


@mcp.tool(
    output_schema=DeleteResult.model_json_schema(),
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
)
async def delete_memory(
    id: int,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> DeleteResult:
    """Delete a memory by ID. Removes from vec index and FTS (via trigger)."""
    dao = MemoryDao(s, uid)
    await dao.delete(id)
    return DeleteResult(success=True, id=id)
