from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from memlord.auth import hash_password
from memlord.dao.api_key import ApiKeyDao
from memlord.dao.user import UserDao
from memlord.db import APISessionDep

from .utils import APIUserDep, templates

router = APIRouter(prefix="/account", tags=["UI"])


@router.get("", response_class=HTMLResponse)
async def account_get(request: Request, s: APISessionDep, user: APIUserDep) -> HTMLResponse:
    api_keys = await ApiKeyDao(s).list_for_user(user.id)
    return templates.TemplateResponse(request, "account.html", {"user": user, "api_keys": api_keys})


@router.post("/display-name")
async def update_display_name(
    request: Request,
    s: APISessionDep,
    user: APIUserDep,
    display_name: str = Form(min_length=1),
) -> Response:
    api_keys = await ApiKeyDao(s).list_for_user(user.id)

    def _err(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "account.html",
            {"user": user, "api_keys": api_keys, "name_error": msg},
            status_code=400,
        )

    display_name = display_name.strip()
    if len(display_name) < 3:
        return _err("Display name must be at least 3 characters.")

    await UserDao(s).update_display_name(user.id, display_name)
    return RedirectResponse("/ui/account?name_updated=1", status_code=303)


@router.post("/change-password")
async def change_password(
    request: Request,
    s: APISessionDep,
    user: APIUserDep,
    current_password: str = Form(),
    new_password: str = Form(min_length=6),
    new_password2: str = Form(min_length=6),
) -> Response:
    api_keys = await ApiKeyDao(s).list_for_user(user.id)

    def _err(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "account.html",
            {"user": user, "api_keys": api_keys, "pw_error": msg},
            status_code=400,
        )

    if new_password != new_password2:
        return _err("New passwords do not match.")

    auth = await UserDao(s).authenticate(user.email, current_password)
    if auth is None:
        return _err("Current password is incorrect.")

    await UserDao(s).set_password(user.id, hash_password(new_password))
    return RedirectResponse("/ui/account?pw_updated=1", status_code=303)


@router.post("/delete")
async def delete_account(
    request: Request,
    s: APISessionDep,
    user: APIUserDep,
    confirm_password: str = Form(),
) -> Response:
    api_keys = await ApiKeyDao(s).list_for_user(user.id)

    def _err(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "account.html",
            {"user": user, "api_keys": api_keys, "delete_error": msg},
            status_code=400,
        )

    auth = await UserDao(s).authenticate(user.email, confirm_password)
    if auth is None:
        return _err("Password is incorrect.")

    await UserDao(s).delete_account(user.id)
    response = RedirectResponse("/ui/login", status_code=303)
    response.delete_cookie("memlord_session")
    return response
