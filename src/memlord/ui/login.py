from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import EmailStr

from memlord.auth import hash_password
from memlord.dao.user import UserDao
from memlord.db import APISessionDep
from .utils import make_session_token, templates

router = APIRouter()


def _set_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        "memlord_session",
        make_session_token(user_id),
        httponly=True,
        samesite="lax",
    )


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, next: str = "/") -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"next": next})


@router.post("/login")
async def login_post(
    request: Request,
    s: APISessionDep,
    email: str = Form(),
    password: str = Form(),
    next: str = Form(default="/"),
) -> Response:
    user = await UserDao(s).authenticate(email, password)

    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": "Incorrect email or password."},
            status_code=401,
        )

    redirect_url = next if next.startswith("/") else "/"
    response = RedirectResponse(redirect_url, status_code=303)
    _set_session(response, user.id)
    return response


@router.post("/logout")
async def logout() -> Response:
    response = RedirectResponse("/ui/login", status_code=303)
    response.delete_cookie("memlord_session")
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_get(request: Request, next: str = "/") -> HTMLResponse:
    return templates.TemplateResponse(request, "register.html", {"next": next})


@router.post("/register")
async def register_post(
    request: Request,
    s: APISessionDep,
    email: EmailStr = Form(),
    display_name: str = Form(),
    password: str = Form(),
    password2: str = Form(),
    next: str = Form(default="/"),
) -> Response:
    def _err(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"next": next, "email": email, "display_name": display_name, "error": msg},
            status_code=400,
        )

    if not display_name.strip():
        return _err("Display name is required.")
    if not password:
        return _err("Password is required.")
    if password != password2:
        return _err("Passwords do not match.")

    if await UserDao(s).exists_by_email(email):
        return _err("An account with this email already exists.")

    user = await UserDao(s).create(
        email=str(email),
        display_name=display_name,
        hashed_password=hash_password(password),
    )

    redirect_url = next if next.startswith("/") else "/"
    response = RedirectResponse(redirect_url, status_code=303)
    _set_session(response, user.id)
    return response
