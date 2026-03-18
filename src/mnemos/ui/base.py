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
from mnemos.models.user import User
from mnemos.schemas import MemoryType, UpdateMemoryRequest
from mnemos.search import hybrid_search
from mnemos.ui.utils import get_current_user, templates
from mnemos.utils.dt import utcnow

router = APIRouter()


_COLS = (
    Memory.id,
    Memory.content,
    Memory.memory_type,
    Memory.created_at,
)


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    s: APISessionDep,
    user: User = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
    memory_type: str | None = None,
    tag: str = "",
) -> HTMLResponse:
    uid: int = user.id  # type: ignore[assignment]
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    q = select(*_COLS).where(Memory.created_by == uid)
    if memory_type:
        q = q.where(Memory.memory_type == MemoryType(memory_type))
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
            **row,
            "tags": tags_map.get(row["id"], []),
        }
        for row in rows
    ]

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "user": user,
            "memories": memories,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "memory_type": memory_type,
            "tag": tag,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    s: APISessionDep,
    user: User = Depends(get_current_user),
    q: str = "",
) -> HTMLResponse:
    uid: int = user.id  # type: ignore[assignment]
    results = []
    if q:
        raw = await hybrid_search(
            s, query=q, user_id=uid, limit=20, similarity_threshold=0.0
        )
        if raw:
            dao = MemoryDao(s)
            ids = [r.id for r in raw]
            tags_map = await dao.fetch_tags(ids)
            created_map = dict(  # type: ignore[arg-type]
                (
                    await s.execute(
                        select(Memory.id, Memory.created_at).where(Memory.id.in_(ids))
                    )
                ).all()
            )
            for r in raw:
                results.append(
                    {
                        "id": r.id,
                        "content": r.content,
                        "memory_type": r.memory_type,
                        "tags": tags_map.get(r.id, []),
                        "created_at": created_map.get(r.id, utcnow()),  # type: ignore[call-overload]
                        "rrf_score": round(r.rrf_score, 4),
                    }
                )
    return templates.TemplateResponse(
        request, "search.html", {"user": user, "q": q, "results": results}
    )


@router.get("/memory/{id}", response_class=HTMLResponse)
async def memory_detail(
    request: Request,
    id: int,
    s: APISessionDep,
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    uid: int = user.id  # type: ignore[assignment]
    memory = await MemoryDao(s).get(id, uid)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return templates.TemplateResponse(
        request, "memory.html", {"user": user, "memory": memory}
    )


@router.put("/memory/{id}", response_class=HTMLResponse)
async def update_memory(
    request: Request,
    id: int,
    s: APISessionDep,
    body: UpdateMemoryRequest,
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    uid: int = user.id  # type: ignore[assignment]
    dao = MemoryDao(s)
    existing = await dao.get(id, uid)
    if existing is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    new_content = (body.content or "").strip() or existing.content
    new_type = (body.memory_type or "").strip() or None
    new_tags = [t.lower().strip() for t in (body.tags or []) if t.strip()]

    data: dict = {
        "id": id,
        "user_id": uid,
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


@router.delete("/memory/{id}")
async def delete_memory_ui(
    id: int,
    s: APISessionDep,
    user: User = Depends(get_current_user),
) -> Response:
    uid: int = user.id  # type: ignore[assignment]
    try:
        await MemoryDao(s).delete(id, uid)
    except ValueError:
        raise HTTPException(status_code=404, detail="Memory not found")
    return Response(content="", status_code=200)
