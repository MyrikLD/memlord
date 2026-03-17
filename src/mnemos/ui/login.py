import secrets

from fastapi import (
    APIRouter,
    Form,
    Request,
    Response,
)
from fastapi.responses import HTMLResponse, RedirectResponse

from mnemos.config import settings
from .utils import session_token, templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, next: str = "/") -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"next": next})


@router.post("/login")
async def login_post(
    request: Request,
    password: str = Form(),
    next: str = Form(default="/"),
) -> Response:
    if not settings.password or not secrets.compare_digest(
        password.encode(), settings.password.encode()
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": "Incorrect password."},
            status_code=401,
        )
    response = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    response.set_cookie(
        "mnemos_session", session_token(), httponly=True, samesite="lax"
    )
    return response
