from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.auth import UserDep
from mnemos.dao import MemoryDao
from mnemos.db import MCPSessionDep
from mnemos.schemas import MemoryType, StoreResult

mcp = FastMCP()


@mcp.tool(
    output_schema=StoreResult.model_json_schema(),
    annotations=ToolAnnotations(idempotentHint=False, destructiveHint=False),
)
async def update_memory(
    id: int,
    memory_type: MemoryType,
    content: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = UserDep,  # type: ignore[assignment]
) -> StoreResult:
    """Update an existing memory by ID. Only provided fields are changed."""
    dao = MemoryDao(s)
    data: dict[str, Any] = {
        "id": id,
        "user_id": uid,
        "memory_type": MemoryType(memory_type),
    }

    if content is not None:
        data["content"] = content
    if metadata is not None:
        data["metadata"] = metadata or {}
    if tags is not None:
        data["tags"] = tags

    memory_id = await dao.update(**data)
    return StoreResult(id=memory_id, created=False)
