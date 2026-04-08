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
