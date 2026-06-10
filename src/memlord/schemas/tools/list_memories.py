from datetime import UTC, datetime

from pydantic import ConfigDict, Field, NaiveDatetime, field_serializer

from ..base import Schema
from ..memory_type import MemoryType
from ..pagination import Paginated


class MemoryItem(Schema):
    """Slim memory record returned by MCP list/search tools (no id, no content)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: set[str]
    created_at: NaiveDatetime
    expires_at: NaiveDatetime | None = None
    workspace: str | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()

    @field_serializer("expires_at")
    def serialize_expires_at(self, v: datetime | None) -> str | None:
        return v.replace(tzinfo=UTC).isoformat() if v else None


class MemoryDetail(Schema):
    """Full memory record returned by get_memory MCP tool."""

    name: str
    content: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: set[str]
    created_at: NaiveDatetime
    expires_at: NaiveDatetime | None = None
    workspace: str | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()

    @field_serializer("expires_at")
    def serialize_expires_at(self, v: datetime | None) -> str | None:
        return v.replace(tzinfo=UTC).isoformat() if v else None


class MemoryPage(Paginated[MemoryItem]): ...
