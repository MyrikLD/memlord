from datetime import datetime, UTC

from pydantic import BaseModel, NaiveDatetime, field_serializer

from .memory_type import MemoryType


class SearchResult(BaseModel):
    id: int
    content: str
    memory_type: MemoryType
    rrf_score: float
    vec_similarity: float | None
    workspace_id: int | None = None


class MemoryResult(BaseModel):
    id: int
    content: str
    memory_type: MemoryType
    tags: set[str]
    metadata: dict
    created_at: NaiveDatetime
    rrf_score: float
    workspace_id: int | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()
