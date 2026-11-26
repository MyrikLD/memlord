from datetime import datetime

from memlord.access import WorkspaceGrant

from .base import Schema


class ApiKeyInfo(Schema):
    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    workspace_grants: dict[int, WorkspaceGrant] | None = None


class ApiKeyCreated(Schema):
    raw: str
