import json
import logging

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import APISessionDep
from memlord.models import Memory
from memlord.schemas import (
    CreateWorkspaceRequest,
    DescriptionRequest,
    InviteRequest,
    InviteResponse,
    RenameRequest,
    WorkspaceDetailResponse,
    WorkspaceInfo,
)
from memlord.schemas.api import ImportItem, ImportResult
from memlord.schemas.workspace import WorkspaceRole
from memlord.ui.utils import APIUserDep
from memlord.utils.dt import utcnow

router = APIRouter(prefix="/workspaces")


@router.get("", response_model=list[WorkspaceInfo])
async def list_workspaces(s: APISessionDep, user: APIUserDep) -> list[WorkspaceInfo]:
    return await WorkspaceDao(s, user.id).list_workspaces()


@router.post("", response_model=WorkspaceInfo, status_code=201)
async def create_workspace(
    s: APISessionDep,
    user: APIUserDep,
    body: CreateWorkspaceRequest,
) -> WorkspaceInfo:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    try:
        return await WorkspaceDao(s, user.id).create(
            name=name, description=body.description.strip() if body.description else None
        )
    except IntegrityError as e:
        raise HTTPException(
            status_code=409, detail=f"A workspace named '{name}' already exists"
        ) from e


@router.post("/join/{token}")
async def use_invite(
    token: str,
    s: APISessionDep,
    user: APIUserDep,
) -> WorkspaceInfo:
    try:
        return await WorkspaceDao(s, user.id).use_invite(token=token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
async def get_workspace(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
) -> WorkspaceDetailResponse:
    dao = WorkspaceDao(s, user.id)
    ws = await dao.get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    members = await dao.get_members(workspace_id)
    return WorkspaceDetailResponse(workspace=ws, members=members)


@router.put("/{workspace_id}/rename", response_model=WorkspaceInfo)
async def rename_workspace(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
    body: RenameRequest,
) -> WorkspaceInfo:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    dao = WorkspaceDao(s, user.id)
    ws = await dao.get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.is_personal:
        raise HTTPException(status_code=400, detail="Cannot rename a personal workspace")
    try:
        await dao.rename(workspace_id=workspace_id, name=name)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    ws = await dao.get_by_id_for_user(workspace_id)
    assert ws is not None
    return ws


@router.put("/{workspace_id}/description", response_model=WorkspaceInfo)
async def update_description(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
    body: DescriptionRequest,
) -> WorkspaceInfo:
    dao = WorkspaceDao(s, user.id)
    ws = await dao.get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        await dao.update_description(
            workspace_id=workspace_id,
            description=body.description.strip() if body.description else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    ws = await dao.get_by_id_for_user(workspace_id)
    assert ws is not None
    return ws


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
) -> None:
    dao = WorkspaceDao(s, user.id)
    ws = await dao.get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.is_personal:
        raise HTTPException(status_code=400, detail="Cannot delete a personal workspace")
    try:
        await dao.delete_workspace(workspace_id=workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{workspace_id}/leave", status_code=204)
async def leave_workspace(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
) -> None:
    dao = WorkspaceDao(s, user.id)
    ws = await dao.get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.is_personal:
        raise HTTPException(status_code=400, detail="Cannot leave a personal workspace")
    try:
        await dao.remove_member(workspace_id=workspace_id, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{workspace_id}/export")
async def export_memories(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
) -> Response:
    ws_dao = WorkspaceDao(s, user.id)
    if not await ws_dao.can_read(workspace_id):
        raise HTTPException(status_code=403, detail="No access to this workspace")
    ws = await ws_dao.get_by_id_for_user(workspace_id)
    assert ws is not None

    ts = utcnow().strftime("%Y%m%d-%H%M")
    ws_slug = "personal" if ws.is_personal else ws.name.replace(" ", "-")
    filename = f"memories-{ws_slug}-{ts}.json"

    rows = (
        (
            await s.execute(
                select(
                    Memory.id,
                    Memory.name,
                    Memory.content,
                    Memory.memory_type,
                    Memory.created_at,
                    Memory.extra_data.label("metadata"),
                )
                .where(Memory.workspace_id == workspace_id)
                .order_by(Memory.created_at)
            )
        )
        .mappings()
        .all()
    )
    ids = [r["id"] for r in rows]
    tags_map = await MemoryDao(s, user.id).fetch_tags(ids) if ids else {}
    data = [
        ImportItem(**r, tags=tags_map.get(r["id"], set())).model_dump(mode="json") for r in rows
    ]
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{workspace_id}/import", response_model=ImportResult)
async def import_memories(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
    file: UploadFile = File(),
) -> ImportResult:
    ws_dao = WorkspaceDao(s, user.id)
    if not await ws_dao.can_write(workspace_id):
        raise HTTPException(status_code=403, detail="No write access to this workspace")
    try:
        items = json.loads(await file.read())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON") from e
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Expected a JSON array")

    dao = MemoryDao(s, user.id)
    imported = skipped = 0
    for item in items:
        try:
            parsed = ImportItem.model_validate(item)
        except Exception as e:
            logging.warning(f"Error {e} during import: {item}")
            skipped += 1
            continue
        _, created = await dao.create(
            content=parsed.content,
            memory_type=parsed.memory_type,
            metadata=parsed.metadata,
            tags=parsed.tags,
            name=parsed.name,
            workspace_id=workspace_id,
            force=True,
        )
        if created:
            imported += 1
        else:
            skipped += 1

    return ImportResult(imported=imported, skipped=skipped)


@router.post("/{workspace_id}/invite", response_model=InviteResponse)
async def create_invite(
    request: Request,
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
    body: InviteRequest,
) -> InviteResponse:
    dao = WorkspaceDao(s, user.id)
    ws = await dao.get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.is_personal:
        raise HTTPException(status_code=400, detail="Cannot invite to a personal workspace")
    if body.role not in (WorkspaceRole.viewer, WorkspaceRole.editor):
        raise HTTPException(status_code=400, detail="Invalid role")
    try:
        token = await dao.create_invite(
            workspace_id=workspace_id,
            expires_in_hours=body.expires_in_hours,
            role=WorkspaceRole(body.role),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    base = str(request.base_url).rstrip("/")
    return InviteResponse(
        invite_url=f"{base}/ui/join/{token}",
        expires_in_hours=body.expires_in_hours,
        role=body.role,
    )
