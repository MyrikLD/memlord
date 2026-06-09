from fastapi import APIRouter, Form, HTTPException

from memlord.dao.api_key import ApiKeyDao
from memlord.db import APISessionDep
from memlord.schemas.api_key import ApiKeyCreated
from memlord.ui.utils import APIUserDep

router = APIRouter(prefix="/api-keys")


@router.post("")
async def create_api_key(
    s: APISessionDep,
    user: APIUserDep,
    name: str = Form(min_length=1),
) -> ApiKeyCreated:
    name = name.strip()
    if await ApiKeyDao(s).name_exists(user.id, name):
        raise HTTPException(status_code=400, detail="A key with this name already exists.")

    raw = await ApiKeyDao(s).create(user.id, name)
    return ApiKeyCreated(raw=raw)


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(s: APISessionDep, user: APIUserDep, key_id: int) -> None:
    if not await ApiKeyDao(s).delete(user.id, key_id):
        raise HTTPException(status_code=404, detail="API key not found.")
