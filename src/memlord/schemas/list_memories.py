from datetime import datetime, UTC

from pydantic import BaseModel, ConfigDict, Field, field_serializer, NaiveDatetime

from .memory_type import MemoryType


class MemoryListItem(BaseModel):
    """Full memory record — used by UI and DAO."""

    id: int
    name: str | None = None
    content: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: set[str]
    created_at: NaiveDatetime
    workspace_id: int

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()


class MemoryItem(BaseModel):
    """Slim memory record returned by MCP list/search tools (no id, no content)."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
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

    name: str | None = None
    content: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: set[str]
    created_at: NaiveDatetime
    workspace: str | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()


class MemoryPage(BaseModel):
    items: list[MemoryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 0
    total_pages: int = 0
