from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mnemos.dao import MemoryDao
from mnemos.db import MCPSessionDep
from mnemos.schemas import StoreResult
from sqlalchemy.ext.asyncio import AsyncSession

mcp = FastMCP()


@mcp.tool(
    output_schema=StoreResult.model_json_schema(),
    annotations=ToolAnnotations(idempotentHint=True, destructiveHint=False),
)
async def store_memory(
    content: str,
    memory_type: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    client_hostname: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
) -> StoreResult:
    """Save a new memory. Idempotent: returns existing if content already stored."""
    dao = MemoryDao(s)
    memory_id, created_at, created = await dao.create(
        content=content,
        memory_type=memory_type,
        metadata=metadata,
        client_hostname=client_hostname,
        tags=tags,
    )
    return StoreResult(id=memory_id, created_at=created_at, created=created)
