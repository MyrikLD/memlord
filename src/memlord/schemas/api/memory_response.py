from datetime import UTC, datetime

from pydantic import NaiveDatetime, field_serializer

from ..base import Schema
from ..pagination import Paginated


class MemoriesFilter(Schema):
    page: int = 1
    page_size: int = 20
    memory_type: str | None = None
    tag: str = ""
    workspace: str = ""


class WorkspaceSimple(Schema):
    id: int
    name: str
    is_personal: bool


def _iso_utc(v: datetime | None) -> str | None:
    """Serialize a naive-UTC timestamp as tz-aware ISO-8601 so clients can localize it."""
    return v.replace(tzinfo=UTC).isoformat() if v else None


class MemoryItem(Schema):
    id: int
    name: str
    content: str
    memory_type: str | None
    created_at: NaiveDatetime
    expires_at: NaiveDatetime | None = None
    workspace_id: int | None
    workspace_name: str | None
    tags: list[str]

    @field_serializer("created_at", "expires_at")
    def _serialize_ts(self, v: datetime | None) -> str | None:
        return _iso_utc(v)


class MemoryDetail(Schema):
    id: int
    name: str
    content: str
    memory_type: str | None
    created_at: NaiveDatetime
    expires_at: NaiveDatetime | None = None
    workspace_id: int | None
    workspace_name: str | None
    tags: list[str]
    metadata: dict | None
    writable_workspaces: list[WorkspaceSimple]

    @field_serializer("created_at", "expires_at")
    def _serialize_ts(self, v: datetime | None) -> str | None:
        return _iso_utc(v)


class MemoriesResponse(Paginated[MemoryItem]): ...


class MoveRequest(Schema):
    to_workspace_id: int
