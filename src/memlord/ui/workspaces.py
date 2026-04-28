from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from memlord.dao.workspace import WorkspaceDao
from memlord.db import APISessionDep
from memlord.ui.utils import APIUserDep, templates

router = APIRouter(prefix='/workspaces')


@router.get("", response_class=HTMLResponse)
async def workspaces_list(request: Request, user: APIUserDep) -> HTMLResponse:
    return templates.TemplateResponse(request, "workspaces.html", {"user": user})


@router.get("/new", response_class=HTMLResponse)
async def workspace_new_get(request: Request, user: APIUserDep) -> HTMLResponse:
    return templates.TemplateResponse(request, "workspace_new.html", {"user": user})


@router.get("/{workspace_id}", response_class=HTMLResponse)
async def workspace_detail(
    request: Request,
    workspace_id: int,
    user: APIUserDep,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "workspace_detail.html",
        {"user": user, "workspace_id": workspace_id},
    )


@router.get("/join/{token}", response_class=HTMLResponse)
async def join_get(
    request: Request,
    token: str,
    s: APISessionDep,
    user: APIUserDep,
) -> HTMLResponse:
    row = await WorkspaceDao(s, user.id).get_invite(token)
    if row is None:
        raise HTTPException(status_code=404, detail="Invalid invite token")
    return templates.TemplateResponse(
        request,
        "workspace_join.html",
        {
            "user": user,
            "token": token,
            "workspace_name": row["workspace_name"],
            "inviter_name": row["inviter_name"],
            "role": row["role"],
            "used": row["used_by"] is not None,
        },
    )
