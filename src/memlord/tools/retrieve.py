from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.config import settings
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas import MemoryResult, MemoryType
from memlord.search import hybrid_search
from memlord.utils.dt import utcnow

mcp = FastMCP()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def retrieve_memory(
    query: str,
    limit: int = 10,
    similarity_threshold: float = settings.sim_threshold,
    memory_type: MemoryType | None = None,
    snippet_length: int = 200,
    workspace: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> list[MemoryResult]:
    """Hybrid semantic + full-text search over stored memories.

    Returns compact snippets by default (snippet_length=200). To get the full
    content of a specific memory, call get_memory(id).
    Set snippet_length=None to return full content immediately.
    Pass workspace=<name> to search only within a specific workspace.
    """
    ws_dao = WorkspaceDao(s)
    if workspace is not None:
        ws = await ws_dao.get_by_name(workspace, uid)
        if ws is None:
            raise ValueError(f"Workspace {workspace!r} not found or not accessible")
        workspace_ids = [ws.id]
    else:
        workspace_ids = await ws_dao.get_accessible_workspace_ids(uid)
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

    output = []
    for r in results:
        metadata, created_at = meta_map.get(r.id, ({}, utcnow()))
        content = r.content
        if snippet_length is not None and len(content) > snippet_length:
            content = content[:snippet_length] + "..."
        output.append(
            MemoryResult(
                id=r.id,
                content=content,
                memory_type=r.memory_type,
                tags=tags_map.get(r.id, []),
                metadata=metadata,
                created_at=created_at,
                rrf_score=r.rrf_score,
                workspace_id=r.workspace_id,
            )
        )
    return output
