from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.models.user import User


class UserDao:
    def __init__(self, s: AsyncSession) -> None:
        self._s = s

    async def get_by_email(self, email: str) -> User | None:
        row = (
            await self._s.execute(
                select(User.hashed_password, User.id).where(User.email == email.strip().lower())
            )
        ).mappings().one_or_none()
        return row

    async def get_by_id(self, id: int) -> User | None:
        row = (
            await self._s.execute(select(User).where(User.id == id))
        ).scalar_one_or_none()
        return row

    async def create(self, email: str, display_name: str, hashed_password: str) -> User:
        user_id = await self._s.scalar(
            insert(User)
            .values(
                email=email.strip().lower(),
                display_name=display_name.strip(),
                hashed_password=hashed_password,
            )
            .returning(User.id)
        )
        assert user_id is not None
        user = await self.get_by_id(user_id)
        assert user is not None
        return user
