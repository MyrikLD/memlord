import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.models.email_token import EmailToken, TokenPurpose
from memlord.utils.dt import utcnow

_TTL: dict[TokenPurpose, timedelta] = {
    TokenPurpose.verify: timedelta(hours=24),
    TokenPurpose.reset: timedelta(hours=1),
}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class EmailTokenDao:
    def __init__(self, s: AsyncSession) -> None:
        self._s = s

    async def create(self, user_id: int, purpose: TokenPurpose) -> str:
        """Create a new token, delete any existing one for same user+purpose, return raw token."""
        await self._s.execute(
            delete(EmailToken).where(
                EmailToken.user_id == user_id,
                EmailToken.purpose == purpose,
            )
        )
        raw = secrets.token_urlsafe(32)
        await self._s.execute(
            insert(EmailToken).values(
                token_hash=_hash(raw),
                user_id=user_id,
                purpose=purpose,
                expires_at=utcnow() + _TTL[purpose],
            )
        )
        return raw

    async def consume(self, raw: str, purpose: TokenPurpose) -> int | None:
        """Validate token; on success delete it and return user_id, else return None."""
        row = (
            (
                await self._s.execute(
                    select(EmailToken.user_id, EmailToken.expires_at).where(
                        EmailToken.token_hash == _hash(raw),
                        EmailToken.purpose == purpose,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if utcnow() > row["expires_at"]:
            return None
        await self._s.execute(delete(EmailToken).where(EmailToken.token_hash == _hash(raw)))
        return row["user_id"]
