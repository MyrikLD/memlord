from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class WorkspaceRole(StrEnum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class WorkspaceInfo(BaseModel):
    id: int
    name: str
    description: str | None
    role: WorkspaceRole
    member_count: int
    is_personal: bool


class WorkspaceMemberInfo(BaseModel):
    user_id: int
    display_name: str
    email: str
    role: WorkspaceRole
    joined_at: datetime


class WorkspaceDetailResponse(BaseModel):
    workspace: WorkspaceInfo
    members: list[WorkspaceMemberInfo]


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str | None = None


class RenameRequest(BaseModel):
    name: str


class DescriptionRequest(BaseModel):
    description: str | None = None


class InviteRequest(BaseModel):
    expires_in_hours: int = 72
    role: str = "viewer"


class InviteResponse(BaseModel):
    invite_url: str
    expires_in_hours: int
    role: str
