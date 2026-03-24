from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import EmailStr

from memlord.auth import hash_password
from memlord.config import settings
from memlord.dao.email_token import EmailTokenDao
from memlord.dao.user import UserDao
from memlord.db import APISessionDep
from memlord.email import send_email
from memlord.models.email_token import TokenPurpose
from .utils import make_session_token, templates, APIUserDep

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

    if settings.smtp_host:
        raw_token = await EmailTokenDao(s).create(user.id, TokenPurpose.verify)
        await send_email(
            to=user.email,
            subject="Verify your Memlord email",
            body=_verify_email_body(raw_token),
        )

    redirect_url = next if next.startswith("/") else "/"
    response = RedirectResponse(redirect_url, status_code=303)
    _set_session(response, user.id)
    return response


def _verify_email_body(token: str) -> str:
    url = f"{settings.base_url}/ui/verify-email?token={token}"
    return (
        f"Hello,\n\n"
        f"Please verify your email address by clicking the link below:\n\n"
        f"{url}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"If you did not create a Memlord account, you can ignore this email.\n"
    )


if settings.smtp_host:

    @router.get("/verify-email", response_class=HTMLResponse)
    async def verify_email(
        request: Request, s: APISessionDep, token: str = ""
    ) -> Response:
        if not token:
            return templates.TemplateResponse(
                request, "verify_email.html", {"error": "Invalid or missing token."}
            )

        user_id = await EmailTokenDao(s).consume(token, TokenPurpose.verify)
        if user_id is None:
            return templates.TemplateResponse(
                request,
                "verify_email.html",
                {"error": "This link is invalid or has expired."},
                status_code=400,
            )

        await UserDao(s).set_email_verified(user_id)
        return templates.TemplateResponse(
            request, "verify_email.html", {"success": True}
        )

    @router.post("/resend-verification")
    async def resend_verification(user: APIUserDep, s: APISessionDep) -> Response:
        user = await UserDao(s).get_by_id(user.id)
        if user is None or user.email_verified:
            return RedirectResponse("/", status_code=303)

        raw_token = await EmailTokenDao(s).create(user.id, TokenPurpose.verify)
        await send_email(
            to=user.email,
            subject="Verify your Memlord email",
            body=_verify_email_body(raw_token),
        )
        return RedirectResponse("/?verification_sent=1", status_code=303)

    def _reset_email_body(token: str) -> str:
        url = f"{settings.base_url}/ui/reset-password?token={token}"
        return (
            f"Hello,\n\n"
            f"You requested a password reset for your Memlord account.\n\n"
            f"Click the link below to set a new password:\n\n"
            f"{url}\n\n"
            f"This link expires in 1 hour.\n\n"
            f"If you did not request this, you can ignore this email.\n"
        )

    @router.get("/forgot-password", response_class=HTMLResponse)
    async def forgot_password_get(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "forgot_password.html", {})

    @router.post("/forgot-password")
    async def forgot_password_post(
        request: Request,
        s: APISessionDep,
        email: str = Form(),
    ) -> Response:
        # Always show success to avoid user enumeration
        user_id = await UserDao(s).get_id_by_email(email)
        if user_id is not None:
            raw_token = await EmailTokenDao(s).create(user_id, TokenPurpose.reset)
            await send_email(
                to=email.strip().lower(),
                subject="Reset your Memlord password",
                body=_reset_email_body(raw_token),
            )

        return templates.TemplateResponse(
            request,
            "forgot_password.html",
            {"sent": True},
        )

    @router.get("/reset-password", response_class=HTMLResponse)
    async def reset_password_get(request: Request, token: str = "") -> HTMLResponse:
        if not token:
            return templates.TemplateResponse(
                request,
                "reset_password.html",
                {"error": "Invalid or missing token."},
                status_code=400,
            )
        return templates.TemplateResponse(
            request, "reset_password.html", {"token": token}
        )

    @router.post("/reset-password")
    async def reset_password_post(
        request: Request,
        s: APISessionDep,
        token: str = Form(),
        password: str = Form(),
        password2: str = Form(),
    ) -> Response:
        def _err(msg: str) -> HTMLResponse:
            return templates.TemplateResponse(
                request,
                "reset_password.html",
                {"token": token, "error": msg},
                status_code=400,
            )

        if not password:
            return _err("Password is required.")
        if password != password2:
            return _err("Passwords do not match.")

        user_id = await EmailTokenDao(s).consume(token, TokenPurpose.reset)
        if user_id is None:
            return _err("This link is invalid or has expired.")

        await UserDao(s).set_password(user_id, hash_password(password))
        return RedirectResponse("/ui/login?reset=1", status_code=303)
