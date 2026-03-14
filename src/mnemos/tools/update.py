from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.dao import MemoryDao
from mnemos.db import MCPSessionDep
from mnemos.schemas import StoreResult

mcp = FastMCP()


@mcp.tool(
    output_schema=StoreResult.model_json_schema(),
    annotations=ToolAnnotations(idempotentHint=False, destructiveHint=False),
)
async def update_memory(
    id: int,
    content: str | None = None,
    memory_type: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
) -> StoreResult:
    """Update an existing memory by ID. Only provided fields are changed."""
    dao = MemoryDao(s)
    data: dict[str, Any] = {
        "id": id,
    }

    if content is not None:
        data["content"] = content
    if memory_type is not None:
        data["memory_type"] = memory_type
    if metadata is not None:
        data["metadata"] = metadata
    if tags is not None:
        data["tags"] = tags

    memory_id, created_at = await dao.update(**data)
    return StoreResult(id=memory_id, created_at=created_at, created=False)
