import hashlib
import hmac
import time
from pathlib import Path
from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, Request
from starlette import status
from starlette.templating import Jinja2Templates

from memlord.config import settings
from memlord.dao.user import UserDao
from memlord.db import APISessionDep
from memlord.schemas import UserInfo

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.globals["smtp_configured"] = bool(settings.smtp_host)

SESSION_TTL = 30 * 24 * 3600  # 30 days


def make_session_token(user_id: int) -> str:
    """Return a signed, time-stamped session token for the given user."""
    ts = int(time.time())
    body = f"{user_id}:{ts}"
    sig = hmac.new(settings.oauth_jwt_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}:{sig}"


def _require_auth(request: Request) -> int:
    """FastAPI dependency: validates session cookie and returns user_id.

    Token format: ``{user_id}:{timestamp}:{hmac_sha256}``
    The HMAC covers ``{user_id}:{timestamp}``, preventing forgery.
    """
    cookie = request.cookies.get("memlord_session", "")
    # Split off the last colon-separated segment as the signature
    idx = cookie.rfind(":")
    if idx < 0:
        _redirect(request)
    body, sig = cookie[:idx], cookie[idx + 1 :]

    expected_sig = hmac.new(
        settings.oauth_jwt_secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        _redirect(request)

    parts = body.split(":", 1)
    if len(parts) != 2:
        _redirect(request)
    try:
        user_id = int(parts[0])
        ts = int(parts[1])
    except ValueError:
        _redirect(request)

    if time.time() - ts > SESSION_TTL:
        _redirect(request)

    return user_id  # type: ignore[return-value]


def _redirect(request: Request) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Location": f"/ui/login?next={request.url.path}"},
    )


async def get_current_user(
    request: Request,
    s: APISessionDep,
    uid: int = Depends(_require_auth),
):
    user = await UserDao(s).get_by_id(uid)
    if user is None:
        _redirect(request)
    return user


APIUserDep = Annotated[UserInfo, Depends(get_current_user)]

__all__ = ["APIUserDep", "make_session_token", "templates"]
