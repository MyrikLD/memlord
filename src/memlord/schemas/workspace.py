from datetime import datetime
from enum import StrEnum

from .base import Schema


class WorkspaceRole(StrEnum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class WorkspaceInfo(Schema):
    id: int
    name: str
    description: str | None
    role: WorkspaceRole
    member_count: int
    is_personal: bool


class WorkspaceMemberInfo(Schema):
    user_id: int
    display_name: str
    email: str
    role: WorkspaceRole
    joined_at: datetime


class WorkspaceDetailResponse(Schema):
    workspace: WorkspaceInfo
    members: list[WorkspaceMemberInfo]


class CreateWorkspaceRequest(Schema):
    name: str
    description: str | None = None


class RenameRequest(Schema):
    name: str


class DescriptionRequest(Schema):
    description: str | None = None


class InviteRequest(Schema):
    expires_in_hours: int = 72
    role: str = "viewer"


class InviteResponse(Schema):
    invite_url: str
    expires_in_hours: int
    role: str
