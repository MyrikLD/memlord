from datetime import UTC, datetime

from pydantic import Field, NaiveDatetime, field_serializer

from .base import Schema
from .memory_type import MemoryType


class MemoryListItem(Schema):
    id: int
    name: str
    content: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: set[str]
    created_at: NaiveDatetime
    expires_at: NaiveDatetime | None = None
    workspace_id: int

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()

    @field_serializer("expires_at")
    def serialize_expires_at(self, v: datetime | None) -> str | None:
        return v.replace(tzinfo=UTC).isoformat() if v else None
