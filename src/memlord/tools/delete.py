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
    name: str,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> DeleteResult:
    """Delete a memory by name."""
    dao = MemoryDao(s, uid)
    memory_id = await dao.get_id_by_name(name)
    if memory_id is None:
        raise ValueError(f"Memory with name={name!r} not found")
    await dao.delete(memory_id)
    return DeleteResult(success=True, name=name)
