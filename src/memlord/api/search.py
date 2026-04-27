from fastapi import APIRouter
from sqlalchemy import select

from memlord.config import settings
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import APISessionDep
from memlord.models import Memory
from memlord.schemas.api import SearchItem, SearchResponse
from memlord.search import hybrid_search
from memlord.ui.utils import APIUserDep

router = APIRouter(prefix="/search")


@router.get("", response_model=SearchResponse)
async def search(
    s: APISessionDep,
    user: APIUserDep,
    q: str = "",
    similarity_threshold: float = settings.sim_threshold,
) -> SearchResponse:
    if not q:
        return SearchResponse(results=[], query=q)

    workspace_ids = await WorkspaceDao(s, user.id).get_accessible_workspace_ids()
    raw = await hybrid_search(
        s,
        query=q,
        workspace_ids=workspace_ids,
        limit=20,
        similarity_threshold=similarity_threshold,
    )

    if not raw:
        return SearchResponse(results=[], query=q)

    ids = [r.id for r in raw]
    tags_map = await MemoryDao(s, user.id).fetch_tags(ids)
    created_map = {
        row.id: row.created_at
        for row in (
            await s.execute(select(Memory.id, Memory.created_at).where(Memory.id.in_(ids)))
        ).all()
    }

    results = [
        SearchItem(
            id=r.id,
            content=r.content,
            memory_type=r.memory_type,
            created_at=created_map[r.id].strftime("%Y-%m-%d %H:%M:%S"),
            workspace_id=None,
            workspace_name=r.workspace,
            tags=sorted(tags_map.get(r.id, set())),
            rrf_score=round(r.rrf_score, 4),
        )
        for r in raw
    ]

    return SearchResponse(results=results, query=q)
