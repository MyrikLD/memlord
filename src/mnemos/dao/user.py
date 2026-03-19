from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.auth import verify_password
from mnemos.dao.workspace import WorkspaceDao
from mnemos.models.user import User
from mnemos.schemas.user import UserInfo


class UserDao:
    def __init__(self, s: AsyncSession) -> None:
        self._s = s

    async def authenticate(self, email: str, password: str) -> UserInfo | None:
        row = (
            (
                await self._s.execute(
                    select(User.id, User.display_name, User.hashed_password).where(
                        User.email == email.strip().lower()
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or not verify_password(password, row["hashed_password"]):
            return None
        return UserInfo(id=row["id"], display_name=row["display_name"])

    async def exists_by_email(self, email: str) -> bool:
        result = await self._s.scalar(
            select(User.id).where(User.email == email.strip().lower())
        )
        return result is not None

    async def get_by_id(self, id: int) -> UserInfo | None:
        row = (
            (
                await self._s.execute(
                    select(User.id, User.display_name).where(User.id == id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return UserInfo(id=row["id"], display_name=row["display_name"])

    async def create(
        self, email: str, display_name: str, hashed_password: str
    ) -> UserInfo:
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
        await WorkspaceDao(self._s).create_personal(user_id)
        return UserInfo(id=user_id, display_name=display_name.strip())
