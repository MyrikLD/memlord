import math

import sqlalchemy as sa
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from mnemos.dao import MemoryDao
from mnemos.db import APISessionDep
from mnemos.models import Memory, MemoryTag, Tag
from mnemos.schemas import UpdateMemoryRequest
from mnemos.search import hybrid_search
from mnemos.ui.utils import require_auth, templates

router = APIRouter()


_COLS = (
    Memory.id,
    Memory.content,
    Memory.memory_type,
    Memory.created_at,
)


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def index(
    request: Request,
    s: APISessionDep,
    page: int = 1,
    page_size: int = 20,
    memory_type: str = "",
    tag: str = "",
) -> HTMLResponse:
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    q = select(*_COLS)
    if memory_type:
        q = q.where(Memory.memory_type == memory_type)
    if tag:
        tag_subq = (
            select(MemoryTag.memory_id)
            .join(Tag, MemoryTag.tag_id == Tag.id)
            .where(Tag.name == tag.lower().strip())
        )
        q = q.where(Memory.id.in_(tag_subq))

    total = await s.scalar(select(sa.func.count()).select_from(q.subquery())) or 0
    rows = (
        (
            await s.execute(
                q.order_by(Memory.created_at.desc()).limit(page_size).offset(offset)
            )
        )
        .mappings()
        .all()
    )
    total_pages = math.ceil(total / page_size) if total else 0
    ids = [row["id"] for row in rows]
    tags_map = await MemoryDao(s).fetch_tags(ids)

    memories = [
        {
            "id": row["id"],
            "content": row["content"],
            "memory_type": row["memory_type"],
            "tags": tags_map.get(row["id"], []),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "memories": memories,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "memory_type": memory_type,
            "tag": tag,
        },
    )


@router.get(
    "/search", response_class=HTMLResponse, dependencies=[Depends(require_auth)]
)
async def search(request: Request, s: APISessionDep, q: str = "") -> HTMLResponse:
    results = []
    if q:
        raw = await hybrid_search(s, query=q, limit=20, similarity_threshold=0.0)
        if raw:
            dao = MemoryDao(s)
            ids = [r.id for r in raw]
            tags_map = await dao.fetch_tags(ids)
            created_map = {
                row.id: row.created_at
                for row in (
                    await s.execute(
                        select(Memory.id, Memory.created_at).where(Memory.id.in_(ids))
                    )
                ).all()
            }
            for r in raw:
                results.append(
                    {
                        "id": r.id,
                        "content": r.content,
                        "memory_type": r.memory_type,
                        "tags": tags_map.get(r.id, []),
                        "created_at": str(created_map.get(r.id, "")),
                        "rrf_score": round(r.rrf_score, 4),
                    }
                )
    return templates.TemplateResponse(
        request, "search.html", {"q": q, "results": results}
    )


@router.get(
    "/memory/{id}", response_class=HTMLResponse, dependencies=[Depends(require_auth)]
)
async def memory_detail(request: Request, id: int, s: APISessionDep) -> HTMLResponse:
    memory = await MemoryDao(s).get(id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return templates.TemplateResponse(request, "memory.html", {"memory": memory})


@router.put(
    "/memory/{id}", response_class=HTMLResponse, dependencies=[Depends(require_auth)]
)
async def update_memory(
    request: Request,
    id: int,
    s: APISessionDep,
    body: UpdateMemoryRequest,
) -> HTMLResponse:
    dao = MemoryDao(s)
    existing = await dao.get(id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    new_content = (body.content or "").strip() or existing.content
    new_type = (body.memory_type or "").strip() or None
    new_tags = [t.lower().strip() for t in (body.tags or []) if t.strip()]

    data: dict = {
        "id": id,
        "memory_type": new_type,
        "metadata": body.metadata,
        "tags": new_tags,
    }
    if new_content != existing.content:
        data["content"] = new_content

    await dao.update(**data)

    return templates.TemplateResponse(
        request,
        "_memory_content.html",
        {
            "memory": {
                "id": id,
                "content": new_content,
                "memory_type": new_type or "",
                "metadata": body.metadata,
                "tags": new_tags,
                "created_at": existing.created_at,
            },
            "success": "Saved.",
        },
    )


@router.delete("/memory/{id}", dependencies=[Depends(require_auth)])
async def delete_memory_ui(id: int, s: APISessionDep) -> Response:
    try:
        await MemoryDao(s).delete(id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Memory not found")
    return Response(content="", status_code=200)
