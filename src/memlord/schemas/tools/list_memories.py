from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, field_serializer

from ..memory_type import MemoryType
from ..pagination import Paginated


class MemoryItem(BaseModel):
    """Slim memory record returned by MCP list/search tools (no id, no content)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: set[str]
    created_at: NaiveDatetime
    workspace: str | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()


class MemoryDetail(BaseModel):
    """Full memory record returned by get_memory MCP tool."""

    name: str
    content: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: set[str]
    created_at: NaiveDatetime
    workspace: str | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()


class MemoryPage(Paginated[MemoryItem]): ...
