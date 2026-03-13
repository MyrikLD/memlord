import hashlib
import hmac
import json
import math
import secrets
from pathlib import Path

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from mnemos.config import settings
from mnemos.db import APISessionDep
from mnemos.embeddings import embed
from mnemos.models import Memory, MemoryTag, Tag
from mnemos.search import hybrid_search
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _fetch_tags(s: AsyncSession, memory_ids: list[int]) -> dict[int, list[str]]:
    if not memory_ids:
        return {}
    rows = await s.execute(
        select(MemoryTag.memory_id, Tag.name)
        .join(Tag, MemoryTag.tag_id == Tag.id)
        .where(MemoryTag.memory_id.in_(memory_ids))
    )
    result: dict[int, list[str]] = {i: [] for i in memory_ids}
    for mid, name in rows.fetchall():
        result[mid].append(name)
    return result


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
    tags_map = await _fetch_tags(s, ids)

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
            ids = [r.id for r in raw]
            tags_map = await _fetch_tags(s, ids)
            meta_rows = (
                (
                    await s.execute(
                        select(Memory.id, Memory.extra_data, Memory.created_at).where(
                            Memory.id.in_(ids)
                        )
                    )
                )
                .mappings()
                .all()
            )
            meta_map = {row["id"]: row for row in meta_rows}
            for r in raw:
                row = meta_map.get(r.id, {})
                results.append(
                    {
                        "id": r.id,
                        "content": r.content,
                        "memory_type": r.memory_type,
                        "tags": tags_map.get(r.id, []),
                        "created_at": str(row.get("created_at", "")),
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

    tags = (await _fetch_tags(s, [id])).get(id, [])
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
    content: str = Form(default=""),
    memory_type: str = Form(default=""),
    tags_str: str = Form(default=""),
    metadata_str: str = Form(default=""),
) -> HTMLResponse:
    row = (
        (await s.execute(select(*_COLS).where(Memory.id == id)))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    # Parse metadata JSON
    new_metadata: dict | None = None
    if metadata_str.strip():
        try:
            new_metadata = json.loads(metadata_str.strip())
        except json.JSONDecodeError:
            tags_now = (await _fetch_tags(s, [id])).get(id, [])
            return templates.TemplateResponse(
                request,
                "_memory_content.html",
                {
                    "memory": {
                        "id": id,
                        "content": content or row["content"],
                        "memory_type": memory_type,
                        "metadata": row["extra_data"],
                        "tags": tags_now,
                        "created_at": str(row["created_at"]),
                    },
                    "error": "Invalid JSON in metadata field.",
                },
                status_code=422,
            )

    update_vals: dict = {}
    new_content = content.strip() or row["content"]
    if new_content != row["content"]:
        update_vals["content"] = new_content
        vector = embed(new_content)
        vec_str = "[" + ",".join(str(v) for v in vector) + "]"
        await s.execute(
            text("DELETE FROM memories_vec WHERE memory_id = :id"), {"id": id}
        )
        await s.execute(
            text("INSERT INTO memories_vec(memory_id, embedding) VALUES (:id, :vec)"),
            {"id": id, "vec": vec_str},
        )

    new_type = memory_type.strip() or None
    if new_type != row["memory_type"]:
        update_vals["memory_type"] = new_type

    if new_metadata != row["extra_data"]:
        update_vals["extra_data"] = new_metadata

    if update_vals:
        await s.execute(update(Memory).where(Memory.id == id).values(**update_vals))

    # Rebuild tags
    await s.execute(delete(MemoryTag).where(MemoryTag.memory_id == id))
    new_tags = [t.strip().lower() for t in tags_str.split(",") if t.strip()]
    for tag_name in new_tags:
        await s.execute(
            sqlite_insert(Tag).values(name=tag_name).on_conflict_do_nothing()
        )
        tag_id = await s.scalar(select(Tag.id).where(Tag.name == tag_name))
        await s.execute(
            sqlite_insert(MemoryTag)
            .values(memory_id=id, tag_id=tag_id)
            .on_conflict_do_nothing()
        )

    updated_memory = {
        "id": id,
        "content": new_content,
        "memory_type": new_type or "",
        "metadata": new_metadata,
        "tags": new_tags,
        "created_at": str(row["created_at"]),
    }
    return templates.TemplateResponse(
        request,
        "_memory_content.html",
        {"memory": updated_memory, "success": "Saved."},
    )


@router.delete("/memory/{id}", dependencies=[Depends(_require_auth)])
async def delete_memory_ui(id: int, s: APISessionDep) -> Response:
    await s.execute(text("DELETE FROM memories_vec WHERE memory_id = :id"), {"id": id})
    result = await s.execute(delete(Memory).where(Memory.id == id).returning(Memory.id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return Response(content="", status_code=200)
