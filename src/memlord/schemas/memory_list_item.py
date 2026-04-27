from datetime import UTC, datetime

from pydantic import BaseModel, Field, NaiveDatetime, field_serializer

from .memory_type import MemoryType


class MemoryListItem(BaseModel):
    id: int
    name: str
    content: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: set[str]
    created_at: NaiveDatetime
    workspace_id: int

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()
