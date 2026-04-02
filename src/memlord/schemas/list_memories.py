from datetime import datetime, UTC

from pydantic import BaseModel, Field, field_serializer, NaiveDatetime

from .memory_type import MemoryType


class MemoryListItem(BaseModel):
    id: int
    content: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: set[str]
    created_at: NaiveDatetime
    workspace_id: int | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()


class MemoryPage(BaseModel):
    items: list[MemoryListItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 0
    total_pages: int = 0
