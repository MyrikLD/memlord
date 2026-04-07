from contextlib import asynccontextmanager

import bcrypt
from fastmcp.server.dependencies import get_access_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastmcp.dependencies import Depends as MCPDepends

from memlord.config import settings
from memlord.db import MCPSessionDep
from memlord.models.oauth_client import OAuthClient


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


async def _current_user_gen(
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
):
    access_token = get_access_token()
    if access_token is None:
        if settings.stdio_user_id is None:
            raise PermissionError("Authentication required")
        yield settings.stdio_user_id
        return
    user_id = await s.scalar(
        select(OAuthClient.user_id).where(OAuthClient.client_id == access_token.client_id)
    )
    if user_id is None:
        raise PermissionError("Unauthenticated")
    yield user_id


MCPUserDep = MCPDepends(asynccontextmanager(_current_user_gen))
