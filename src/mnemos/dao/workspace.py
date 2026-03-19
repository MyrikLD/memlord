import uuid
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.models.user import User
from mnemos.models.workspace import Workspace, WorkspaceInvite, WorkspaceMember
from mnemos.schemas.workspace import WorkspaceInfo, WorkspaceMemberInfo


class WorkspaceDao:
    def __init__(self, s: AsyncSession) -> None:
        self._s = s

    async def create(self, name: str, owner_id: int) -> WorkspaceInfo:
        workspace_id = await self._s.scalar(
            insert(Workspace)
            .values(name=name, created_by=owner_id, is_personal=False)
            .returning(Workspace.id)
        )
        assert workspace_id is not None
        await self._s.execute(
            insert(WorkspaceMember).values(
                workspace_id=workspace_id, user_id=owner_id, role="owner"
            )
        )
        return WorkspaceInfo(
            id=workspace_id, name=name, role="owner", member_count=1, is_personal=False
        )

    async def create_personal(self, user_id: int) -> WorkspaceInfo:
        """Create a personal workspace for user_id and add them as owner."""
        name = f"__personal_{user_id}__"
        workspace_id = await self._s.scalar(
            insert(Workspace)
            .values(name=name, created_by=user_id, is_personal=True)
            .returning(Workspace.id)
        )
        assert workspace_id is not None
        await self._s.execute(
            insert(WorkspaceMember).values(
                workspace_id=workspace_id, user_id=user_id, role="owner"
            )
        )
        return WorkspaceInfo(
            id=workspace_id, name=name, role="owner", member_count=1, is_personal=True
        )

    async def get_personal(self, user_id: int) -> WorkspaceInfo:
        """Return the personal workspace for user_id. Raises if not found."""
        member_count_subq = (
            select(sa.func.count())
            .where(WorkspaceMember.workspace_id == Workspace.id)
            .correlate(Workspace)
            .scalar_subquery()
        )
        row = (
            (
                await self._s.execute(
                    select(
                        Workspace.id,
                        Workspace.name,
                        Workspace.is_personal,
                        WorkspaceMember.role,
                        member_count_subq.label("member_count"),
                    )
                    .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                    .where(
                        Workspace.created_by == user_id,
                        Workspace.is_personal.is_(True),
                        WorkspaceMember.user_id == user_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ValueError(f"Personal workspace not found for user {user_id}")
        return WorkspaceInfo(
            id=row["id"],
            name=row["name"],
            role=row["role"],
            member_count=row["member_count"],
            is_personal=True,
        )

    async def can_write(self, workspace_id: int, user_id: int) -> bool:
        """True if user has owner or editor role in the workspace."""
        role = await self.get_role(workspace_id, user_id)
        return role in ("owner", "editor")

    async def can_read(self, workspace_id: int, user_id: int) -> bool:
        """True if user is any member of the workspace."""
        role = await self.get_role(workspace_id, user_id)
        return role is not None

    async def get_role(self, workspace_id: int, user_id: int) -> str | None:
        return await self._s.scalar(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )

    async def add_member(
        self, workspace_id: int, user_id: int, role: str = "member"
    ) -> None:
        await self._s.execute(
            insert(WorkspaceMember).values(
                workspace_id=workspace_id, user_id=user_id, role=role
            )
        )

    async def remove_member(self, workspace_id: int, user_id: int) -> None:
        role = await self.get_role(workspace_id, user_id)
        if role is None:
            raise ValueError(f"Not a member of workspace {workspace_id}")
        if role == "owner":
            raise ValueError(
                "Owners cannot leave a workspace. Delete the workspace instead."
            )
        await self._s.execute(
            delete(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )

    async def delete_workspace(self, workspace_id: int, owner_id: int) -> None:
        role = await self.get_role(workspace_id, owner_id)
        if role != "owner":
            raise ValueError("Only the owner can delete a workspace")
        await self._s.execute(delete(Workspace).where(Workspace.id == workspace_id))

    async def get_accessible_workspace_ids(self, user_id: int) -> list[int]:
        rows = await self._s.scalars(
            select(WorkspaceMember.workspace_id).where(
                WorkspaceMember.user_id == user_id
            )
        )
        return list(rows)

    async def list_workspaces(self, user_id: int) -> list[WorkspaceInfo]:
        member_count_subq = (
            select(sa.func.count())
            .where(WorkspaceMember.workspace_id == Workspace.id)
            .correlate(Workspace)
            .scalar_subquery()
        )
        rows = (
            (
                await self._s.execute(
                    select(
                        Workspace.id,
                        Workspace.name,
                        Workspace.is_personal,
                        WorkspaceMember.role,
                        member_count_subq.label("member_count"),
                    )
                    .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                    .where(WorkspaceMember.user_id == user_id)
                    .order_by(Workspace.name)
                )
            )
            .mappings()
            .all()
        )
        return [
            WorkspaceInfo(
                id=row["id"],
                name=row["name"],
                role=row["role"],
                member_count=row["member_count"],
                is_personal=row["is_personal"],
            )
            for row in rows
        ]

    async def get_by_name(self, name: str, user_id: int) -> WorkspaceInfo | None:
        """Find a workspace by name among workspaces accessible to user_id."""
        member_count_subq = (
            select(sa.func.count())
            .where(WorkspaceMember.workspace_id == Workspace.id)
            .correlate(Workspace)
            .scalar_subquery()
        )
        row = (
            (
                await self._s.execute(
                    select(
                        Workspace.id,
                        Workspace.name,
                        Workspace.is_personal,
                        WorkspaceMember.role,
                        member_count_subq.label("member_count"),
                    )
                    .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                    .where(Workspace.name == name, WorkspaceMember.user_id == user_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return WorkspaceInfo(
            id=row["id"],
            name=row["name"],
            role=row["role"],
            member_count=row["member_count"],
            is_personal=row["is_personal"],
        )

    async def get_by_id_for_user(
        self, workspace_id: int, user_id: int
    ) -> WorkspaceInfo | None:
        member_count_subq = (
            select(sa.func.count())
            .where(WorkspaceMember.workspace_id == workspace_id)
            .scalar_subquery()
        )
        row = (
            (
                await self._s.execute(
                    select(
                        Workspace.id,
                        Workspace.name,
                        Workspace.is_personal,
                        WorkspaceMember.role,
                        member_count_subq.label("member_count"),
                    )
                    .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                    .where(
                        Workspace.id == workspace_id, WorkspaceMember.user_id == user_id
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return WorkspaceInfo(
            id=row["id"],
            name=row["name"],
            role=row["role"],
            member_count=row["member_count"],
            is_personal=row["is_personal"],
        )

    async def get_members(self, workspace_id: int) -> list[WorkspaceMemberInfo]:
        rows = (
            (
                await self._s.execute(
                    select(
                        WorkspaceMember.user_id,
                        WorkspaceMember.role,
                        WorkspaceMember.joined_at,
                        User.display_name,
                        User.email,
                    )
                    .join(User, User.id == WorkspaceMember.user_id)
                    .where(WorkspaceMember.workspace_id == workspace_id)
                    .order_by(WorkspaceMember.joined_at)
                )
            )
            .mappings()
            .all()
        )
        return [
            WorkspaceMemberInfo(
                user_id=row["user_id"],
                display_name=row["display_name"],
                email=row["email"],
                role=row["role"],
                joined_at=row["joined_at"],
            )
            for row in rows
        ]

    async def create_invite(
        self, workspace_id: int, created_by: int, expires_in_hours: int = 72
    ) -> str:
        role = await self.get_role(workspace_id, created_by)
        if role is None:
            raise ValueError(f"Not a member of workspace {workspace_id}")
        token = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
        await self._s.execute(
            insert(WorkspaceInvite).values(
                id=token,
                workspace_id=workspace_id,
                created_by=created_by,
                expires_at=expires_at,
            )
        )
        return token

    async def get_invite(self, token: str):
        return (
            (
                await self._s.execute(
                    select(
                        WorkspaceInvite.id,
                        WorkspaceInvite.workspace_id,
                        WorkspaceInvite.expires_at,
                        WorkspaceInvite.used_by,
                        Workspace.name.label("workspace_name"),
                        User.display_name.label("inviter_name"),
                    )
                    .join(Workspace, Workspace.id == WorkspaceInvite.workspace_id)
                    .join(User, User.id == WorkspaceInvite.created_by)
                    .where(WorkspaceInvite.id == token)
                )
            )
            .mappings()
            .one_or_none()
        )

    async def use_invite(self, token: str, user_id: int) -> WorkspaceInfo:
        row = await self.get_invite(token)
        if row is None:
            raise ValueError("Invalid invite token")
        if row["used_by"] is not None:
            raise ValueError("Invite has already been used")
        if row["expires_at"] < datetime.utcnow():
            raise ValueError("Invite has expired")

        workspace_id = row["workspace_id"]
        existing_role = await self.get_role(workspace_id, user_id)
        if existing_role is not None:
            raise ValueError("Already a member of this workspace")

        await self._s.execute(
            update(WorkspaceInvite)
            .where(WorkspaceInvite.id == token)
            .values(used_by=user_id, used_at=datetime.utcnow())
        )
        await self.add_member(workspace_id, user_id, role="member")

        ws_info = await self.get_by_id_for_user(workspace_id, user_id)
        assert ws_info is not None
        return ws_info

    async def get_names_by_ids(self, workspace_ids: set[int]) -> dict[int, str]:
        if not workspace_ids:
            return {}
        rows = await self._s.execute(
            select(Workspace.id, Workspace.name).where(Workspace.id.in_(workspace_ids))
        )
        return {row.id: row.name for row in rows.fetchall()}
