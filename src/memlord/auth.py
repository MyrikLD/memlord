import hashlib
import secrets
from contextlib import asynccontextmanager

import bcrypt
from fastmcp.dependencies import Depends as MCPDepends
from fastmcp.server.dependencies import get_access_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.db import MCPSessionDep
from memlord.models.oauth_client import OAuthClient


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# API keys are opaque random tokens sent as `Authorization: Bearer mk_...`.
# Only their SHA-256 hash is stored; the raw key is shown once at creation.
API_KEY_PREFIX = "mk_"
# Synthetic OAuth client_id we stamp onto the AccessToken so the user resolves
# without a second DB lookup in _current_user_gen.
API_KEY_CLIENT_PREFIX = "apikey:"


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _current_user_gen(
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
):
    access_token = get_access_token()
    if access_token is None:
        raise PermissionError("Authentication required")
    # API-key auth stamps the user id into client_id (see oauth.load_access_token).
    if access_token.client_id.startswith(API_KEY_CLIENT_PREFIX):
        yield int(access_token.client_id.removeprefix(API_KEY_CLIENT_PREFIX))
        return
    user_id = await s.scalar(
        select(OAuthClient.user_id).where(OAuthClient.client_id == access_token.client_id)
    )
    if user_id is None:
        raise PermissionError("Unauthenticated")
    yield user_id


MCPUserDep = MCPDepends(asynccontextmanager(_current_user_gen))
