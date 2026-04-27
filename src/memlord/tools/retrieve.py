from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.config import settings
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas import MemoryType
from memlord.schemas.tools import MemoryResult
from memlord.search import hybrid_search
from memlord.utils.dt import utcnow

mcp = FastMCP()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def retrieve_memory(
    query: str = Field(..., description="Query string"),
    limit: int = Field(10, ge=1),
    similarity_threshold: float = settings.sim_threshold,
    memory_type: MemoryType | None = None,
    workspace: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> list[MemoryResult]:
    """Hybrid semantic + full-text search. Returns names + metadata only.

    Use get_memory(name=...) to fetch full content of a specific result.
    Pass workspace=<name> to search only within a specific workspace.
    """
    ws_dao = WorkspaceDao(s, uid)
    if workspace is not None:
        ws = await ws_dao.get_by_name(workspace)
        if ws is None:
            raise ValueError(f"Workspace {workspace!r} not found")
        workspace_ids = [ws.id]
    else:
        workspace_ids = await ws_dao.get_accessible_workspace_ids()
    results = await hybrid_search(
        s,
        query=query,
        workspace_ids=workspace_ids,
        limit=limit,
        similarity_threshold=similarity_threshold,
        memory_type=memory_type,
    )

    if not results:
        return []

    dao = MemoryDao(s, uid)
    ids = [r.id for r in results]
    tags_map = await dao.fetch_tags(ids)
    meta_map = await dao.fetch_metadata(ids)

    return [
        MemoryResult(
            name=r.name,
            memory_type=r.memory_type,
            tags=tags_map.get(r.id, set()),
            metadata=meta_map.get(r.id, ({}, utcnow()))[0],
            created_at=meta_map.get(r.id, ({}, utcnow()))[1],
            rrf_score=r.rrf_score,
            workspace=r.workspace,
        )
        for r in results
    ]
