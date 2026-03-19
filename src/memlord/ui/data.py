import json
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette import status

from memlord.dao import MemoryDao
from memlord.db import APISessionDep
from memlord.models import Memory
from memlord.schemas import ImportItem
from memlord.ui.utils import require_auth

router = APIRouter()


@router.get("/export")
async def export_memories_ui(
    s: APISessionDep,
    uid: int = Depends(require_auth),
) -> Response:
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
                .where(Memory.created_by == uid)
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
        headers={"Content-Disposition": "attachment; filename=memories.json"},
    )


@router.post("/import")
async def import_memories_ui(
    s: APISessionDep,
    file: UploadFile = File(),
    uid: int = Depends(require_auth),
) -> Response:
    try:
        items = json.loads(await file.read())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Expected a JSON array")

    from memlord.dao.workspace import WorkspaceDao

    personal_ws = await WorkspaceDao(s).get_personal(uid)
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
            workspace_id=personal_ws.id,
        )
        if created:
            imported += 1
        else:
            skipped += 1

    return RedirectResponse(
        f"/?imported={imported}&skipped={skipped}",
        status_code=status.HTTP_303_SEE_OTHER,
    )