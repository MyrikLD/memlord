from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
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
    annotations=ToolAnnotations(idempotentHint=False, destructiveHint=False),
)
async def update_memory(
    name: str,
    memory_type: MemoryType,
    content: str | None = None,
    new_name: str | None = None,
    tags: set[str] | None = None,
    metadata: dict | None = None,
    workspace: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> StoreResult:
    """Update an existing memory identified by name. Only provided fields are changed.

    new_name: rename the memory to this name.
    workspace: disambiguate if the name exists in multiple workspaces.
    """
    ws_id: int | None = None
    if workspace is not None:
        ws = await WorkspaceDao(s, uid).get_by_name(workspace)
        if ws is None:
            raise ValueError(f"Workspace {workspace!r} not found")
        ws_id = ws.id
    dao = MemoryDao(s, uid)
    item = await dao.get(name=name, workspace_id=ws_id)
    if item is None:
        raise ValueError(f"Memory with name={name!r} not found")

    data: dict[str, Any] = {
        "id": item.id,
        "workspace_id": item.workspace_id,
        "memory_type": MemoryType(memory_type),
    }

    if content is not None:
        data["content"] = content
    if metadata is not None:
        data["metadata"] = metadata or {}
    if tags is not None:
        data["tags"] = tags
    if new_name is not None:
        data["name"] = new_name

    _, final_name = await dao.update(**data)
    return StoreResult(name=final_name, created=False)
