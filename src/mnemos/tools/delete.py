from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mnemos.db import MCPSessionDep
from mnemos.models import Memory
from mnemos.schemas import DeleteResult
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

mcp = FastMCP()


@mcp.tool(
    output_schema=DeleteResult.model_json_schema(),
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
)
async def delete_memory(id: int, s: AsyncSession = MCPSessionDep) -> DeleteResult:  # type: ignore[assignment]
    """Delete a memory by ID. Removes from vec index and FTS (via trigger)."""
    # Delete from vec index manually (no trigger for vec0)
    await s.execute(text("DELETE FROM memories_vec WHERE memory_id = :id"), {"id": id})

    # Delete from memories (CASCADE → memory_tags; trigger → memories_fts)
    row = await s.execute(delete(Memory).where(Memory.id == id).returning(Memory.id))
    if row.scalar_one_or_none() is None:
        raise ValueError(f"Memory with id={id} not found")

    return DeleteResult(success=True, id=id)
