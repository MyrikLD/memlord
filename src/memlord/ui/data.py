import json
import logging
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette import status

from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import APISessionDep
from memlord.models import Memory
from memlord.schemas import ImportItem
from memlord.ui.utils import require_auth

router = APIRouter()


@router.get("/export")
async def export_memories_ui(
    s: APISessionDep,
    workspace_id: int,
    uid: int = Depends(require_auth),
) -> Response:
    ws_dao = WorkspaceDao(s)
    if not await ws_dao.can_read(workspace_id, uid):
        raise HTTPException(status_code=403, detail="No access to this workspace")

    ws = await ws_dao.get_by_id_for_user(workspace_id, uid)
    assert ws is not None

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M")
    ws_slug = "personal" if ws.is_personal else ws.name.replace(" ", "-")
    filename = f"memories-{ws_slug}-{ts}.json"

    rows = (
        (
            await s.execute(
                select(
                    Memory.id,
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
    tags_map = await MemoryDao(s, uid).fetch_tags(ids) if ids else {}
    data = [
        ImportItem(
            **r,
            tags=tags_map.get(r["id"], []),
        ).model_dump(mode="json")
        for r in rows
    ]
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/import")
async def import_memories_ui(
    s: APISessionDep,
    file: UploadFile = File(),
    uid: int = Depends(require_auth),
    workspace_id: str | None = Form(None),
) -> Response:
    try:
        items = json.loads(await file.read())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Expected a JSON array")

    ws_dao = WorkspaceDao(s)
    ws_id: int | None = int(workspace_id) if workspace_id else None
    if ws_id is not None:
        if not await ws_dao.can_write(ws_id, uid):
            raise HTTPException(status_code=403, detail="No write access to this workspace")
        target_ws_id = ws_id
    else:
        personal_ws = await ws_dao.get_personal(uid)
        target_ws_id = personal_ws.id

    dao = MemoryDao(s, uid)
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
            workspace_id=target_ws_id,
            force=True,
        )
        if created:
            imported += 1
        else:
            skipped += 1

    redirect_target = (
        f"/ui/workspaces/{target_ws_id}?imported={imported}&skipped={skipped}"
    )
    return RedirectResponse(redirect_target, status_code=status.HTTP_303_SEE_OTHER)