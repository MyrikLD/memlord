from fastapi import APIRouter, HTTPException

from memlord.dao import TagDao
from memlord.db import APISessionDep
from memlord.schemas.tag import (
    TagDetachRequest,
    TagGroup,
    TagMergeRequest,
)
from memlord.ui.utils import APIUserDep

router = APIRouter(prefix="/workspaces/{workspace_id}/tags")


def _http(e: Exception) -> HTTPException:
    if isinstance(e, PermissionError):
        return HTTPException(status_code=403, detail=str(e))
    return HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[TagGroup])
async def list_tags(workspace_id: int, s: APISessionDep, user: APIUserDep) -> list[TagGroup]:
    try:
        return await TagDao(s, user.id).list_groups(workspace_id)
    except (PermissionError, ValueError) as e:
        raise _http(e) from e


@router.post("/merge", response_model=TagGroup)
async def merge_tags(
    workspace_id: int, body: TagMergeRequest, s: APISessionDep, user: APIUserDep
) -> TagGroup:
    try:
        return await TagDao(s, user.id).merge(workspace_id, body.source, body.target)
    except (PermissionError, ValueError) as e:
        raise _http(e) from e


@router.post("/detach", response_model=TagGroup)
async def detach_alias(
    workspace_id: int, body: TagDetachRequest, s: APISessionDep, user: APIUserDep
) -> TagGroup:
    try:
        return await TagDao(s, user.id).detach(workspace_id, body.alias)
    except (PermissionError, ValueError) as e:
        raise _http(e) from e
