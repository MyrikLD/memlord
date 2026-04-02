from datetime import datetime, UTC

from pydantic import BaseModel, Field, field_serializer, NaiveDatetime

from .memory_type import MemoryType


class RecallResult(BaseModel):
    id: int
    content: str
    memory_type: MemoryType | None
    tags: set[str]
    created_at: NaiveDatetime
    workspace_id: int | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()


class RecallPage(BaseModel):
    items: list[RecallResult] = Field(default_factory=list)
