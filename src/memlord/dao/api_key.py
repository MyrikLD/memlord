from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import generate_api_key, hash_api_key
from memlord.models.api_key import ApiKey
from memlord.schemas.api_key import ApiKeyInfo


class ApiKeyDao:
    def __init__(self, s: AsyncSession) -> None:
        self._s = s

    async def create(self, user_id: int, name: str) -> tuple[str, ApiKeyInfo]:
        """Create a key for the user. Returns the raw token (shown once) and its metadata."""
        raw = generate_api_key()
        prefix = raw[:11]
        row = (
            (
                await self._s.execute(
                    insert(ApiKey)
                    .values(
                        user_id=user_id,
                        name=name.strip(),
                        token_hash=hash_api_key(raw),
                        prefix=prefix,
                    )
                    .returning(ApiKey.id, ApiKey.created_at)
                )
            )
            .mappings()
            .one()
        )
        info = ApiKeyInfo(
            id=row["id"],
            name=name.strip(),
            prefix=prefix,
            created_at=row["created_at"],
            last_used_at=None,
        )
        return raw, info

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

    async def delete(self, user_id: int, key_id: int) -> None:
        await self._s.execute(delete(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))

    async def resolve_user(self, raw: str) -> int | None:
        """Validate a raw key and return its owner, bumping last_used_at. None if unknown."""
        user_id = await self._s.scalar(
            update(ApiKey)
            .where(ApiKey.token_hash == hash_api_key(raw))
            .values(last_used_at=func.now())
            .returning(ApiKey.user_id)
        )
        return user_id
