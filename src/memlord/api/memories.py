import sqlalchemy as sa
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import APISessionDep
from memlord.filters import has_tag, not_expired
from memlord.models import Memory
from memlord.schemas import MemoryListItem, MemoryType
from memlord.schemas.api import (
    MemoriesFilter,
    MemoriesResponse,
    MemoryDetail,
    MemoryItem,
    MoveRequest,
    UpdateMemoryRequest,
    WorkspaceSimple,
)
from memlord.schemas.workspace import WorkspaceInfo, WorkspaceRole
from memlord.tags import normalize_tag
from memlord.ui.utils import APIUserDep
from memlord.utils.dt import as_naive_utc

router = APIRouter(prefix="/memories")

_COLS = (
    Memory.id,
    Memory.name,
    Memory.content,
    Memory.memory_type,
    Memory.created_at,
    Memory.expires_at,
    Memory.workspace_id,
)


@router.post("", response_model=MemoriesResponse)
async def list_memories(
    s: APISessionDep,
    user: APIUserDep,
    body: MemoriesFilter,
) -> MemoriesResponse:
    page_size = min(body.page_size, 100)
    offset = (body.page - 1) * page_size

    ws_dao = WorkspaceDao(s, user.id)
    workspaces = await ws_dao.list_workspaces()
    workspace_ids = [ws.id for ws in workspaces]

    if body.workspace == "__personal__":
        personal = next((ws for ws in workspaces if ws.is_personal), None)
        access_filter = (
            Memory.workspace_id == personal.id if personal else Memory.workspace_id.in_([])
        )
    elif body.workspace:
        ws_obj = next((ws for ws in workspaces if ws.name == body.workspace), None)
        access_filter = (
            Memory.workspace_id == ws_obj.id
            if ws_obj is not None
            else Memory.workspace_id.in_(workspace_ids)
        )
    else:
        access_filter = Memory.workspace_id.in_(workspace_ids)

    q = select(*_COLS).where(access_filter, not_expired())

    if body.memory_type:
        q = q.where(Memory.memory_type == MemoryType(body.memory_type))
    if body.tag:
        wanted = normalize_tag(body.tag)
        q = q.where(has_tag(lambda t: t.name == wanted))

    total = await s.scalar(select(sa.func.count()).select_from(q.subquery())) or 0
    rows = (
        (await s.execute(q.order_by(Memory.created_at.desc()).limit(page_size).offset(offset)))
        .mappings()
        .all()
    )
    ids = [row["id"] for row in rows]
    tags_map = await MemoryDao(s, user.id).fetch_tags(ids)
    ws_display = {ws.id: ("Personal" if ws.is_personal else ws.name) for ws in workspaces}

    memories = [
        MemoryItem(
            id=row["id"],
            name=row["name"],
            content=row["content"],
            memory_type=row["memory_type"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            workspace_id=row["workspace_id"],
            workspace_name=ws_display.get(row["workspace_id"]) if row["workspace_id"] else None,
            tags=sorted(tags_map.get(row["id"], set())),
        )
        for row in rows
    ]

    return MemoriesResponse(
        items=memories,
        total=total,
        page=body.page,
        page_size=page_size,
    )


def _build_detail(
    memory: MemoryListItem, original_tags: set[str], workspaces: list[WorkspaceInfo]
) -> MemoryDetail:
    ws_map = {ws.id: ("Personal" if ws.is_personal else ws.name) for ws in workspaces}
    writable = [
        WorkspaceSimple(id=ws.id, name=ws.name, is_personal=ws.is_personal)
        for ws in workspaces
        if ws.role in (WorkspaceRole.owner, WorkspaceRole.editor) and ws.id != memory.workspace_id
    ]
    return MemoryDetail(
        id=memory.id,
        name=memory.name,
        content=memory.content,
        memory_type=memory.memory_type,
        created_at=memory.created_at,
        expires_at=memory.expires_at,
        workspace_id=memory.workspace_id,
        workspace_name=ws_map.get(memory.workspace_id) if memory.workspace_id else None,
        tags=sorted(memory.tags),
        original_tags=sorted(original_tags),
        metadata=memory.metadata or None,
        writable_workspaces=writable,
    )


async def _detail(s, dao: MemoryDao, memory: MemoryListItem, uid: int) -> MemoryDetail:
    original = (await dao.fetch_original_tags([memory.id]))[memory.id]
    workspaces = await WorkspaceDao(s, uid).list_workspaces()
    return _build_detail(memory, original, workspaces)


@router.get("/{workspace_id}/{id}", response_model=MemoryDetail)
async def get_memory(
    id: int,
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
) -> MemoryDetail:
    dao = MemoryDao(s, user.id)
    memory = await dao.get(id=id, workspace_id=workspace_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return await _detail(s, dao, memory, user.id)


@router.put("/{workspace_id}/{id}", response_model=MemoryDetail)
async def update_memory(
    id: int,
    workspace_id: int,
    s: APISessionDep,
    body: UpdateMemoryRequest,
    user: APIUserDep,
) -> MemoryDetail:
    dao = MemoryDao(s, user.id)
    existing = await dao.get(id=id, workspace_id=workspace_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    new_content = (body.content or "").strip() or existing.content
    new_type = (body.memory_type or "").strip()
    data: dict = {
        "id": id,
        "workspace_id": existing.workspace_id,
        "metadata": body.metadata,
    }
    if new_type:
        data["memory_type"] = new_type
    if body.tags is not None:
        data["tags"] = {normalize_tag(t) for t in body.tags} - {""}
    if new_content != existing.content:
        data["content"] = new_content
    if body.name is not None:
        data["name"] = body.name
    if "expires_at" in body.model_fields_set:
        # Explicit null clears expiry; a value sets it; omitted leaves it unchanged.
        # Normalize to naive UTC to match how timestamps are stored.
        data["expires_at"] = as_naive_utc(body.expires_at)

    await dao.update(**data)

    # Re-read the updated row so the response is built from a validated, correctly
    # typed record (rather than hand-mutating the pre-update DTO).
    updated = await dao.get(id=id, workspace_id=existing.workspace_id)
    if updated is None:
        # Only reachable if the row vanished concurrently: get() returns
        # expired memories, so a past expiry no longer hides the record.
        raise HTTPException(status_code=404, detail="Memory not found after update")
    return await _detail(s, dao, updated, user.id)


@router.delete("/{workspace_id}/{id}", status_code=204)
async def delete_memory(
    id: int,
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
) -> None:
    try:
        await MemoryDao(s, user.id).delete(id, workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Memory not found") from e


@router.post("/{workspace_id}/{id}/move", response_model=MemoryDetail)
async def move_memory(
    id: int,
    workspace_id: int,
    body: MoveRequest,
    s: APISessionDep,
    user: APIUserDep,
) -> MemoryDetail:
    dao = MemoryDao(s, user.id)
    memory = await dao.get(id=id, workspace_id=workspace_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    try:
        await dao.move(id, workspace_id, body.to_workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    moved = await dao.get(id=id, workspace_id=body.to_workspace_id)
    if moved is None:
        raise HTTPException(status_code=404, detail="Memory not found after move")
    return await _detail(s, dao, moved, user.id)
