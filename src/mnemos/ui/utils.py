import hashlib
import hmac
from pathlib import Path

from fastapi import (
    HTTPException,
    Request,
)
from starlette.templating import Jinja2Templates

from mnemos.config import settings

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def session_token() -> str:
    return hmac.new(
        settings.password.encode(), b"mnemos-ui-session", hashlib.sha256
    ).hexdigest()


def require_auth(request: Request) -> None:
    if not settings.password:
        return
    token = request.cookies.get("mnemos_session")
    if not token or not hmac.compare_digest(token, session_token()):
        raise HTTPException(
            status_code=307, headers={"Location": f"/ui/login?next={request.url.path}"}
        )
