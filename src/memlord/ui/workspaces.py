from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.exc import IntegrityError

from memlord.dao.workspace import WorkspaceDao
from memlord.db import APISessionDep
from memlord.ui.utils import templates, APIUserDep

router = APIRouter()


@router.get("/workspaces", response_class=HTMLResponse)
async def workspaces_list(
    request: Request,
    s: APISessionDep,
    user: APIUserDep,
) -> HTMLResponse:
    workspaces = await WorkspaceDao(s, user.id).list_workspaces()
    return templates.TemplateResponse(
        request, "workspaces.html", {"user": user, "workspaces": workspaces}
    )


@router.get("/workspaces/new", response_class=HTMLResponse)
async def workspace_new_get(
    request: Request,
    user: APIUserDep,
) -> HTMLResponse:
    return templates.TemplateResponse(request, "workspace_new.html", {"user": user})


@router.post("/workspaces/new")
async def workspace_new_post(
    request: Request,
    s: APISessionDep,
    user: APIUserDep,
    name: str = Form(),
    description: str = Form(default=""),
) -> Response:
    name = name.strip()
    description_val = description.strip() or None
    if not name:
        return templates.TemplateResponse(
            request,
            "workspace_new.html",
            {"user": user, "error": "Name is required.", "name": name},
            status_code=400,
        )
    try:
        ws = await WorkspaceDao(s, user.id).create(name=name, description=description_val)
    except IntegrityError:
        return templates.TemplateResponse(
            request,
            "workspace_new.html",
            {
                "user": user,
                "error": f"A workspace named '{name}' already exists.",
                "name": name,
                "description": description,
            },
            status_code=400,
        )
    return RedirectResponse(f"/ui/workspaces/{ws.id}", status_code=303)


@router.get("/workspaces/{workspace_id}", response_class=HTMLResponse)
async def workspace_detail(
    request: Request,
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
) -> HTMLResponse:
    dao = WorkspaceDao(s, user.id)
    ws = await dao.get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    members = await dao.get_members(workspace_id)
    return templates.TemplateResponse(
        request,
        "workspace_detail.html",
        {"user": user, "workspace": ws, "members": members},
    )


@router.post("/workspaces/{workspace_id}/rename")
async def workspace_rename_post(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
    name: str = Form(),
) -> Response:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    ws = await WorkspaceDao(s, user.id).get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.is_personal:
        raise HTTPException(status_code=400, detail="Cannot rename a personal workspace")
    try:
        await WorkspaceDao(s, user.id).rename(workspace_id=workspace_id, name=name)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return RedirectResponse(f"/ui/workspaces/{workspace_id}", status_code=303)


@router.post("/workspaces/{workspace_id}/description")
async def workspace_description_post(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
    description: str = Form(default=""),
) -> Response:
    ws = await WorkspaceDao(s, user.id).get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        await WorkspaceDao(s, user.id).update_description(
            workspace_id=workspace_id,
            description=description.strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return RedirectResponse(f"/ui/workspaces/{workspace_id}", status_code=303)


@router.post("/workspaces/{workspace_id}/invite", response_class=HTMLResponse)
async def workspace_invite(
    request: Request,
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
    expires_in_hours: int = Form(default=72),
) -> HTMLResponse:
    ws = await WorkspaceDao(s, user.id).get_by_id_for_user(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.is_personal:
        raise HTTPException(status_code=400, detail="Cannot invite to a personal workspace")
    try:
        token = await WorkspaceDao(s, user.id).create_invite(
            workspace_id=workspace_id,
            expires_in_hours=expires_in_hours,
        )
    except ValueError as e:
        return HTMLResponse(f'<div class="alert alert-error">{e}</div>', status_code=400)
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
    user: APIUserDep,
) -> Response:
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
    return RedirectResponse("/ui/workspaces", status_code=303)


@router.post("/workspaces/{workspace_id}/delete")
async def workspace_delete(
    workspace_id: int,
    s: APISessionDep,
    user: APIUserDep,
) -> Response:
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
    return RedirectResponse("/ui/workspaces", status_code=303)


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
            "used": row["used_by"] is not None,
        },
    )


@router.post("/join/{token}")
async def join_post(
    token: str,
    s: APISessionDep,
    user: APIUserDep,
) -> Response:
    try:
        ws = await WorkspaceDao(s, user.id).use_invite(token=token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return RedirectResponse(f"/ui/workspaces/{ws.id}", status_code=303)
