from datetime import datetime

from pydantic import BaseModel

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
    created_at: datetime
    rrf_score: float
    workspace_id: int | None = None
