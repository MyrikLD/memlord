import math

import sqlalchemy as sa
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from mnemos.dao import MemoryDao
from mnemos.dao.workspace import WorkspaceDao
from mnemos.db import APISessionDep
from mnemos.models import Memory, MemoryTag, Tag
from mnemos.schemas import MemoryType, UpdateMemoryRequest
from mnemos.search import hybrid_search
from mnemos.ui.utils import get_current_user, templates, UserDep
from mnemos.utils.dt import utcnow

router = APIRouter()


_COLS = (
    Memory.id,
    Memory.content,
    Memory.memory_type,
    Memory.created_at,
    Memory.workspace_id,
)


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    s: APISessionDep,
    user: UserDep,
    page: int = 1,
    page_size: int = 20,
    memory_type: str | None = None,
    tag: str = "",
    workspace: str = "",
) -> HTMLResponse:
    uid: int = user.id
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    ws_dao = WorkspaceDao(s)
    workspaces = await ws_dao.list_workspaces(uid)
    workspace_ids = [ws.id for ws in workspaces]

    # Apply workspace filter
    if workspace == "__personal__":
        personal = next((ws for ws in workspaces if ws.is_personal), None)
        access_filter = (
            Memory.workspace_id == personal.id
            if personal
            else Memory.workspace_id.in_([])
        )
    elif workspace:
        ws_obj = next((ws for ws in workspaces if ws.name == workspace), None)
        access_filter = (
            Memory.workspace_id == ws_obj.id
            if ws_obj is not None
            else Memory.workspace_id.in_(workspace_ids)
        )
    else:
        access_filter = Memory.workspace_id.in_(workspace_ids)

    q = select(*_COLS).where(access_filter)

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
    tags_map = await MemoryDao(s, uid).fetch_tags(ids)

    ws_display = {
        ws.id: ("Personal" if ws.is_personal else ws.name) for ws in workspaces
    }

    memories = [
        {
            **row,
            "tags": tags_map.get(row["id"], []),
            "workspace_name": (
                ws_display.get(row["workspace_id"]) if row["workspace_id"] else None
            ),
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
            "workspace": workspace,
            "workspaces": workspaces,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    s: APISessionDep,
    user: UserDep,
    q: str = "",
) -> HTMLResponse:
    uid: int = user.id
    results = []
    if q:
        workspace_ids = await WorkspaceDao(s).get_accessible_workspace_ids(uid)
        raw = await hybrid_search(
            s,
            query=q,
            workspace_ids=workspace_ids,
            limit=20,
            similarity_threshold=0.0,
        )
        if raw:
            dao = MemoryDao(s, uid)
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
            ws_ids = {r.workspace_id for r in raw if r.workspace_id}
            ws_names = await WorkspaceDao(s).get_names_by_ids(ws_ids) if ws_ids else {}

            for r in raw:
                results.append(
                    {
                        "id": r.id,
                        "content": r.content,
                        "memory_type": r.memory_type,
                        "tags": tags_map.get(r.id, []),
                        "created_at": created_map.get(r.id, utcnow()),  # type: ignore[call-overload]
                        "rrf_score": round(r.rrf_score, 4),
                        "workspace_name": (
                            ws_names.get(r.workspace_id) if r.workspace_id else None
                        ),
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
    user: UserDep,
) -> HTMLResponse:
    uid: int = user.id
    memory = await MemoryDao(s, uid).get(id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    workspaces = await WorkspaceDao(s).list_workspaces(uid)
    ws_map = {ws.id: ("Personal" if ws.is_personal else ws.name) for ws in workspaces}
    ws_name = ws_map.get(memory.workspace_id) if memory.workspace_id else None
    writable = [
        ws
        for ws in workspaces
        if ws.role in ("owner", "editor") and ws.id != memory.workspace_id
    ]

    return templates.TemplateResponse(
        request,
        "memory.html",
        {
            "user": user,
            "memory": memory,
            "workspace_name": ws_name,
            "writable_workspaces": writable,
        },
    )


@router.put("/memory/{id}", response_class=HTMLResponse)
async def update_memory(
    request: Request,
    id: int,
    s: APISessionDep,
    body: UpdateMemoryRequest,
    user: UserDep,
) -> HTMLResponse:
    uid: int = user.id
    dao = MemoryDao(s, uid)
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

    workspaces = await WorkspaceDao(s).list_workspaces(uid)
    ws_map = {ws.id: ("Personal" if ws.is_personal else ws.name) for ws in workspaces}
    ws_name = ws_map.get(existing.workspace_id) if existing.workspace_id else None
    writable = [
        ws
        for ws in workspaces
        if ws.role in ("owner", "editor") and ws.id != existing.workspace_id
    ]

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
                "workspace_id": existing.workspace_id,
            },
            "workspace_name": ws_name,
            "writable_workspaces": writable,
            "success": "Saved.",
        },
    )


@router.post("/memory/{id}/move", response_class=HTMLResponse)
async def move_memory(
    request: Request,
    id: int,
    s: APISessionDep,
    user: UserDep,
    target_workspace_id: int = Form(...),
) -> HTMLResponse:
    uid: int = user.id
    ws_dao = WorkspaceDao(s)
    dao = MemoryDao(s, uid)
    try:
        await dao.move(id, target_workspace_id)
    except ValueError as e:
        memory = await dao.get(id)
        if memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        workspaces = await ws_dao.list_workspaces(uid)
        ws_map = {
            ws.id: ("Personal" if ws.is_personal else ws.name) for ws in workspaces
        }
        ws_name = ws_map.get(memory.workspace_id) if memory.workspace_id else None
        writable = [
            ws
            for ws in workspaces
            if ws.role in ("owner", "editor") and ws.id != memory.workspace_id
        ]
        return templates.TemplateResponse(
            request,
            "_memory_content.html",
            {
                "user": user,
                "memory": memory,
                "workspace_name": ws_name,
                "writable_workspaces": writable,
                "error": str(e),
            },
        )

    memory = await dao.get(id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    workspaces = await ws_dao.list_workspaces(uid)
    ws_map = {ws.id: ("Personal" if ws.is_personal else ws.name) for ws in workspaces}
    ws_name = ws_map.get(memory.workspace_id) if memory.workspace_id else None
    writable = [
        ws
        for ws in workspaces
        if ws.role in ("owner", "editor") and ws.id != memory.workspace_id
    ]
    return templates.TemplateResponse(
        request,
        "_memory_content.html",
        {
            "user": user,
            "memory": memory,
            "workspace_name": ws_name,
            "writable_workspaces": writable,
            "success": "Moved.",
        },
    )


@router.delete("/memory/{id}")
async def delete_memory_ui(
    id: int,
    s: APISessionDep,
    user: UserDep,
) -> Response:
    uid: int = user.id
    try:
        await MemoryDao(s, uid).delete(id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Memory not found")
    return Response(content="", status_code=200)
