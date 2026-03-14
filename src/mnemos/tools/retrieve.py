from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mnemos.dao import MemoryDao
from mnemos.db import MCPSessionDep
from mnemos.schemas import MemoryResult
from mnemos.search import hybrid_search
from sqlalchemy.ext.asyncio import AsyncSession

mcp = FastMCP()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def retrieve_memory(
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.7,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
) -> list[MemoryResult]:
    """Hybrid semantic + full-text search over stored memories."""
    results = await hybrid_search(
        s,
        query=query,
        limit=limit,
        similarity_threshold=similarity_threshold,
    )

    if not results:
        return []

    dao = MemoryDao(s)
    ids = [r.id for r in results]
    tags_map = await dao.fetch_tags(ids)
    meta_map = await dao.fetch_metadata(ids)

    output = []
    for r in results:
        metadata, created_at = meta_map.get(r.id, (None, None))
        output.append(
            MemoryResult(
                id=r.id,
                content=r.content,
                memory_type=r.memory_type,
                tags=tags_map.get(r.id, []),
                metadata=metadata,
                created_at=str(created_at) if created_at else None,
                rrf_score=r.rrf_score,
            )
        )
    return output
