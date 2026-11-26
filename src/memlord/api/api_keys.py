from typing import Literal

from fastapi import APIRouter, Form, HTTPException, Request

from memlord.access import WorkspaceGrant
from memlord.config import settings
from memlord.dao.api_key import ApiKeyDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import APISessionDep
from memlord.schemas.api_key import ApiKeyCreated
from memlord.ui.utils import APIUserDep

router = APIRouter(prefix="/api-keys")
ScopeMode = Literal["account", "restricted"]


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin != settings.base_url.rstrip("/"):
        raise HTTPException(status_code=403, detail="Invalid request origin.")


async def _parse_grants(
    workspaces: WorkspaceDao, mode: ScopeMode, values: list[str] | None
) -> dict[int, WorkspaceGrant] | None:
    values = [value for value in values or [] if value]
    if mode == "account":
        if values:
            raise HTTPException(status_code=400, detail="Choose either account access or workspace grants.")
        return None
    grants = {}
    for value in values:
        try:
            identifier, permission = value.split(":", 1)
            workspace_id = int(identifier)
            grant = WorkspaceGrant(permission)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid workspace grant.") from None
        if workspace_id <= 0 or workspace_id in grants:
            raise HTTPException(status_code=400, detail="Invalid or repeated workspace.")
        grants[workspace_id] = grant
    readable = set(await workspaces.get_accessible_workspace_ids())
    writable = set(await workspaces.get_accessible_workspace_ids(write=True))
    if not grants.keys() <= readable or any(
        workspace_id not in writable for workspace_id, grant in grants.items()
        if grant == WorkspaceGrant.write
    ):
        raise HTTPException(status_code=403, detail="A key cannot exceed the account's workspace access.")
    return grants


@router.post("")
async def create_api_key(
    request: Request,
    s: APISessionDep,
    user: APIUserDep,
    name: str = Form(min_length=1),
    scope_mode: ScopeMode | None = Form(None),
    grants: list[str] | None = Form(None),
) -> ApiKeyCreated:
    _check_origin(request)
    name = name.strip()
    dao = ApiKeyDao(s)
    if not name:
        raise HTTPException(status_code=400, detail="Enter a key name.")
    if await dao.name_exists(user.id, name):
        raise HTTPException(status_code=400, detail="A key with this name already exists.")
    # Legacy clients sending only a name retain the existing account-wide behavior.
    mode = scope_mode or ("restricted" if grants is not None else "account")
    workspace_grants = await _parse_grants(WorkspaceDao(s, user.id), mode, grants)
    return ApiKeyCreated(raw=await dao.create(user.id, name, workspace_grants))


@router.patch("/{key_id}/scope", status_code=204)
async def update_scope(
    request: Request,
    s: APISessionDep,
    user: APIUserDep,
    key_id: int,
    scope_mode: ScopeMode = Form(),
    grants: list[str] | None = Form(None),
) -> None:
    _check_origin(request)
    workspace_grants = await _parse_grants(WorkspaceDao(s, user.id), scope_mode, grants)
    if not await ApiKeyDao(s).set_grants(user.id, key_id, workspace_grants):
        raise HTTPException(status_code=404, detail="API key not found.")


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(request: Request, s: APISessionDep, user: APIUserDep, key_id: int) -> None:
    _check_origin(request)
    if not await ApiKeyDao(s).delete(user.id, key_id):
        raise HTTPException(status_code=404, detail="API key not found.")
