from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.exc import IntegrityError

from mnemos.dao.workspace import WorkspaceDao
from mnemos.db import APISessionDep
from mnemos.ui.utils import templates, UserDep

router = APIRouter()


@router.get("/workspaces", response_class=HTMLResponse)
async def workspaces_list(
    request: Request,
    s: APISessionDep,
    user: UserDep,
) -> HTMLResponse:
    uid: int = user.id
    workspaces = await WorkspaceDao(s).list_workspaces(user_id=uid)
    return templates.TemplateResponse(
        request, "workspaces.html", {"user": user, "workspaces": workspaces}
    )


@router.get("/workspaces/new", response_class=HTMLResponse)
async def workspace_new_get(
    request: Request,
    user: UserDep,
) -> HTMLResponse:
    return templates.TemplateResponse(request, "workspace_new.html", {"user": user})


@router.post("/workspaces/new")
async def workspace_new_post(
    request: Request,
    s: APISessionDep,
    user: UserDep,
    name: str = Form(),
) -> Response:
    uid: int = user.id
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            request,
            "workspace_new.html",
            {"user": user, "error": "Name is required.", "name": name},
            status_code=400,
        )
    try:
        ws = await WorkspaceDao(s).create(name=name, owner_id=uid)
    except IntegrityError:
        return templates.TemplateResponse(
            request,
            "workspace_new.html",
            {
                "user": user,
                "error": f"A workspace named '{name}' already exists.",
                "name": name,
            },
            status_code=400,
        )
    return RedirectResponse(f"/ui/workspaces/{ws.id}", status_code=303)


@router.get("/workspaces/{workspace_id}", response_class=HTMLResponse)
async def workspace_detail(
    request: Request,
    workspace_id: int,
    s: APISessionDep,
    user: UserDep,
) -> HTMLResponse:
    uid: int = user.id
    dao = WorkspaceDao(s)
    ws = await dao.get_by_id_for_user(workspace_id, uid)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    members = await dao.get_members(workspace_id)
    return templates.TemplateResponse(
        request,
        "workspace_detail.html",
        {"user": user, "workspace": ws, "members": members},
    )


@router.post("/workspaces/{workspace_id}/invite", response_class=HTMLResponse)
async def workspace_invite(
    request: Request,
    workspace_id: int,
    s: APISessionDep,
    user: UserDep,
    expires_in_hours: int = Form(default=72),
) -> HTMLResponse:
    uid: int = user.id
    ws = await WorkspaceDao(s).get_by_id_for_user(workspace_id, uid)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.is_personal:
        raise HTTPException(
            status_code=400, detail="Cannot invite to a personal workspace"
        )
    try:
        token = await WorkspaceDao(s).create_invite(
            workspace_id=workspace_id,
            created_by=uid,
            expires_in_hours=expires_in_hours,
        )
    except ValueError as e:
        return HTMLResponse(
            f'<div class="alert alert-error">{e}</div>', status_code=400
        )
    base = str(request.base_url).rstrip("/")
    invite_url = f"{base}/ui/join/{token}"
    return templates.TemplateResponse(
        request,
        "_invite_link.html",
        {"invite_url": invite_url, "expires_in_hours": expires_in_hours},
    )


@router.post("/workspaces/{workspace_id}/leave")
async def workspace_leave(
    workspace_id: int,
    s: APISessionDep,
    user: UserDep,
) -> Response:
    uid: int = user.id
    dao = WorkspaceDao(s)
    ws = await dao.get_by_id_for_user(workspace_id, uid)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.is_personal:
        raise HTTPException(status_code=400, detail="Cannot leave a personal workspace")
    try:
        await dao.remove_member(workspace_id=workspace_id, user_id=uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse("/ui/workspaces", status_code=303)


@router.post("/workspaces/{workspace_id}/delete")
async def workspace_delete(
    workspace_id: int,
    s: APISessionDep,
    user: UserDep,
) -> Response:
    uid: int = user.id
    dao = WorkspaceDao(s)
    ws = await dao.get_by_id_for_user(workspace_id, uid)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.is_personal:
        raise HTTPException(
            status_code=400, detail="Cannot delete a personal workspace"
        )
    try:
        await dao.delete_workspace(workspace_id=workspace_id, owner_id=uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse("/ui/workspaces", status_code=303)


@router.get("/join/{token}", response_class=HTMLResponse)
async def join_get(
    request: Request,
    token: str,
    s: APISessionDep,
    user: UserDep,
) -> HTMLResponse:
    row = await WorkspaceDao(s).get_invite(token)
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
            "used": row["used_by"] is not None,
        },
    )


@router.post("/join/{token}")
async def join_post(
    token: str,
    s: APISessionDep,
    user: UserDep,
) -> Response:
    uid: int = user.id
    try:
        ws = await WorkspaceDao(s).use_invite(token=token, user_id=uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(f"/ui/workspaces/{ws.id}", status_code=303)
