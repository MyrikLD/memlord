from datetime import UTC, datetime

from pydantic import BaseModel, NaiveDatetime, field_serializer

from ..memory_type import MemoryType


class MemoryResult(BaseModel):
    name: str
    memory_type: MemoryType
    tags: set[str]
    metadata: dict
    created_at: NaiveDatetime
    rrf_score: float
    workspace: str | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()
