from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import generate_api_key, hash_api_key
from memlord.models.api_key import ApiKey
from memlord.schemas.api_key import ApiKeyInfo


class ApiKeyDao:
    def __init__(self, s: AsyncSession) -> None:
        self._s = s

    async def create(self, user_id: int, name: str) -> str:
        """Create a key for the user and return the raw token (shown once).

        Metadata (id, prefix, timestamps) is available via `list_for_user`.
        """
        raw = generate_api_key()
        await self._s.execute(
            insert(ApiKey).values(
                user_id=user_id,
                name=name.strip(),
                token_hash=hash_api_key(raw),
                prefix=raw[:11],
            )
        )
        return raw

    async def list_for_user(self, user_id: int) -> list[ApiKeyInfo]:
        rows = await self._s.execute(
            select(
                ApiKey.id,
                ApiKey.name,
                ApiKey.prefix,
                ApiKey.created_at,
                ApiKey.last_used_at,
            )
            .where(ApiKey.user_id == user_id)
            .order_by(ApiKey.created_at.desc())
        )
        return [ApiKeyInfo(**r) for r in rows.mappings().all()]

    async def name_exists(self, user_id: int, name: str) -> bool:
        result = await self._s.scalar(
            select(ApiKey.id).where(ApiKey.user_id == user_id, ApiKey.name == name.strip())
        )
        return result is not None

    async def delete(self, user_id: int, key_id: int) -> bool:
        """Delete the user's key. Returns False if no such key existed for them."""
        result = await self._s.scalar(
            delete(ApiKey)
            .where(ApiKey.id == key_id, ApiKey.user_id == user_id)
            .returning(ApiKey.id)
        )
        return result is not None

    async def resolve_user(self, raw: str) -> int | None:
        """Validate a raw key and return its owner, bumping last_used_at. None if unknown."""
        user_id = await self._s.scalar(
            update(ApiKey)
            .where(ApiKey.token_hash == hash_api_key(raw))
            .values(last_used_at=func.now())
            .returning(ApiKey.user_id)
        )
        return user_id
