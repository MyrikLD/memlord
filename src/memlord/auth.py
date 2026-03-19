from contextlib import asynccontextmanager

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastmcp.dependencies import CurrentAccessToken, Depends as MCPDepends
from fastmcp.server.auth.auth import AccessToken

from memlord.db import MCPSessionDep
from memlord.models.oauth_client import OAuthClient


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


async def _current_user_gen(
    access_token: AccessToken = CurrentAccessToken(),  # type: ignore[assignment]
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
):
    if access_token is None:
        raise PermissionError("Authentication required")
    user_id = await s.scalar(
        select(OAuthClient.user_id).where(
            OAuthClient.client_id == access_token.client_id
        )
    )
    if user_id is None:
        raise PermissionError("Unauthenticated")
    yield user_id


UserDep = MCPDepends(asynccontextmanager(_current_user_gen))
