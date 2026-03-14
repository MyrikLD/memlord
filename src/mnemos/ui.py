import hashlib
import hmac
import math
import secrets
from pathlib import Path

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from mnemos.config import settings
from mnemos.dao import MemoryDao
from mnemos.db import APISessionDep
from mnemos.models import Memory, MemoryTag, Tag
from mnemos.schemas import UpdateMemoryRequest
from mnemos.search import hybrid_search

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _session_token() -> str:
    return hmac.new(
        settings.password.encode(), b"mnemos-ui-session", hashlib.sha256
    ).hexdigest()


def _require_auth(request: Request) -> None:
    if not settings.password:
        return
    token = request.cookies.get("mnemos_session")
    if not token or not hmac.compare_digest(token, _session_token()):
        raise HTTPException(
            status_code=307, headers={"Location": f"/ui/login?next={request.url.path}"}
        )


_COLS = (
    Memory.id,
    Memory.content,
    Memory.memory_type,
    Memory.extra_data,
    Memory.created_at,
)


@router.get("/ui/login", response_class=HTMLResponse)
async def login_get(request: Request, next: str = "/") -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"next": next})


@router.post("/ui/login")
async def login_post(
    request: Request,
    password: str = Form(),
    next: str = Form(default="/"),
) -> Response:
    if not settings.password or not secrets.compare_digest(
        password.encode(), settings.password.encode()
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": "Incorrect password."},
            status_code=401,
        )
    response = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    response.set_cookie(
        "mnemos_session", _session_token(), httponly=True, samesite="lax"
    )
    return response


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(_require_auth)])
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
    "/search", response_class=HTMLResponse, dependencies=[Depends(_require_auth)]
)
async def search(request: Request, s: APISessionDep, q: str = "") -> HTMLResponse:
    results = []
    if q:
        raw = await hybrid_search(s, query=q, limit=20, similarity_threshold=0.0)
        if raw:
            dao = MemoryDao(s)
            ids = [r.id for r in raw]
            tags_map = await dao.fetch_tags(ids)
            meta_map = await dao.fetch_metadata(ids)
            for r in raw:
                extra_data, created_at = meta_map.get(r.id, (None, None))
                results.append(
                    {
                        "id": r.id,
                        "content": r.content,
                        "memory_type": r.memory_type,
                        "tags": tags_map.get(r.id, []),
                        "created_at": str(created_at) if created_at else "",
                        "rrf_score": round(r.rrf_score, 4),
                    }
                )
    return templates.TemplateResponse(
        request, "search.html", {"q": q, "results": results}
    )


@router.get(
    "/memory/{id}", response_class=HTMLResponse, dependencies=[Depends(_require_auth)]
)
async def memory_detail(request: Request, id: int, s: APISessionDep) -> HTMLResponse:
    row = (
        (await s.execute(select(*_COLS).where(Memory.id == id)))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    tags = (await MemoryDao(s).fetch_tags([id])).get(id, [])
    memory = {
        "id": row["id"],
        "content": row["content"],
        "memory_type": row["memory_type"] or "",
        "metadata": row["extra_data"],
        "tags": tags,
        "created_at": str(row["created_at"]),
    }
    return templates.TemplateResponse(request, "memory.html", {"memory": memory})


@router.put(
    "/memory/{id}", response_class=HTMLResponse, dependencies=[Depends(_require_auth)]
)
async def update_memory(
    request: Request,
    id: int,
    s: APISessionDep,
    body: UpdateMemoryRequest,
) -> HTMLResponse:
    row = (
        (await s.execute(select(*_COLS).where(Memory.id == id)))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    dao = MemoryDao(s)
    new_content = (body.content or "").strip() or row["content"]
    new_type = (body.memory_type or "").strip() or None
    new_tags = [t.lower().strip() for t in (body.tags or []) if t.strip()]

    data = {
        "id": id,
        "memory_type": new_type,
        "metadata": body.metadata,
        "tags": new_tags,
    }
    if new_content != row["content"]:
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
                "created_at": str(row["created_at"]),
            },
            "success": "Saved.",
        },
    )


@router.delete("/memory/{id}", dependencies=[Depends(_require_auth)])
async def delete_memory_ui(id: int, s: APISessionDep) -> Response:
    try:
        await MemoryDao(s).delete(id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Memory not found")
    return Response(content="", status_code=200)
