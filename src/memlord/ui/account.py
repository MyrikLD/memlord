import base64

import pyotp
import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from memlord.auth import hash_password
from memlord.dao import MemoryDao
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


@router.post("/purge-expired")
async def purge_expired(s: APISessionDep, user: APIUserDep) -> RedirectResponse:
    count = await MemoryDao(s, user.id).purge_expired()
    return RedirectResponse(f"/ui/account?purged={count}", status_code=303)


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


@router.get("/2fa", response_class=HTMLResponse)
async def totp_setup_get(request: Request, user: APIUserDep) -> Response:
    if user.totp_enabled:
        return templates.TemplateResponse(
            request, "totp_setup.html", {"user": user, "totp_enabled": True}
        )

    secret = pyotp.random_base32()
    email = user.email or user.display_name
    uri = pyotp.TOTP(secret).provisioning_uri(email, issuer_name="Memlord")
    qr_svg = (
        "data:image/svg+xml;base64,"
        + base64.b64encode(
            qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage).to_string()
        ).decode()
    )

    return templates.TemplateResponse(
        request,
        "totp_setup.html",
        {"user": user, "totp_enabled": False, "qr_svg": qr_svg, "secret": secret},
    )


@router.post("/2fa/enable")
async def totp_enable(
    request: Request,
    s: APISessionDep,
    user: APIUserDep,
    code: str = Form(),
    secret: str = Form(default=""),
) -> Response:
    if not secret:
        return RedirectResponse("/ui/account/2fa", status_code=303)

    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        email = user.email or user.display_name
        uri = pyotp.TOTP(secret).provisioning_uri(email, issuer_name="Memlord")
        qr_svg = (
            "data:image/svg+xml;base64,"
            + base64.b64encode(
                qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage).to_string()
            ).decode()
        )
        return templates.TemplateResponse(
            request,
            "totp_setup.html",
            {
                "user": user,
                "totp_enabled": False,
                "qr_svg": qr_svg,
                "secret": secret,
                "error": "Invalid code. Please try again.",
            },
            status_code=400,
        )

    await UserDao(s).set_totp_secret(user.id, secret)
    return RedirectResponse("/ui/account/2fa?totp_enabled=1", status_code=303)


@router.post("/2fa/disable")
async def totp_disable(
    request: Request,
    s: APISessionDep,
    user: APIUserDep,
    current_password: str = Form(),
) -> Response:
    auth = await UserDao(s).authenticate(user.email, current_password)
    if auth is None:
        return templates.TemplateResponse(
            request,
            "totp_setup.html",
            {"user": user, "totp_enabled": True, "error": "Incorrect password."},
            status_code=400,
        )

    await UserDao(s).set_totp_secret(user.id, None)
    return RedirectResponse("/ui/account/2fa?totp_disabled=1", status_code=303)


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
