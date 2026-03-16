from pydantic import BaseModel

from .memory_type import MemoryType


class SearchResult(BaseModel):
    id: int
    content: str
    memory_type: MemoryType
    rrf_score: float
    vec_similarity: float | None


class MemoryResult(BaseModel):
    id: int
    content: str
    memory_type: MemoryType
    tags: list[str]
    metadata: dict | None
    created_at: str | None
    rrf_score: float
