from datetime import UTC, datetime

from pydantic import BaseModel, Field, NaiveDatetime, field_serializer

from ..memory_type import MemoryType


class RecallResult(BaseModel):
    name: str
    memory_type: MemoryType | None
    tags: set[str]
    created_at: NaiveDatetime
    workspace: str | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()


class RecallPage(BaseModel):
    items: list[RecallResult] = Field(default_factory=list)
