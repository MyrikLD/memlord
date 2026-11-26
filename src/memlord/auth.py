import hashlib
import secrets
from contextlib import asynccontextmanager

import bcrypt
from fastmcp.dependencies import Depends as MCPDepends
from fastmcp.server.dependencies import get_access_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.access import Principal, WorkspaceGrant
from memlord.db import MCPSessionDep
from memlord.models.api_key import ApiKey
from memlord.models.oauth_client import OAuthClient


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# API keys are opaque random tokens sent as `Authorization: Bearer mk_...`.
# Only their SHA-256 hash is stored; the raw key is shown once at creation.
API_KEY_PREFIX = "mk_"
# Synthetic client ID for authenticated API keys.
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
    if access_token.token.startswith(API_KEY_PREFIX):
        if not access_token.client_id.startswith(API_KEY_CLIENT_PREFIX):
            raise PermissionError("Unauthenticated")
        key_id = int(access_token.client_id.removeprefix(API_KEY_CLIENT_PREFIX))
        row = (
            await s.execute(select(ApiKey.user_id, ApiKey.workspace_grants).where(ApiKey.id == key_id))
        ).one_or_none()
        if row is None:
            raise PermissionError("Unauthenticated")
        stored = row.workspace_grants
        grants = (
            {int(workspace_id): WorkspaceGrant(mode) for workspace_id, mode in stored.items()}
            if stored is not None
            else None
        )
        yield Principal(row.user_id, grants)
        return
    user_id = await s.scalar(
        select(OAuthClient.user_id).where(OAuthClient.client_id == access_token.client_id)
    )
    if user_id is None:
        raise PermissionError("Unauthenticated")
    yield Principal(user_id)


MCPUserDep = MCPDepends(asynccontextmanager(_current_user_gen))
