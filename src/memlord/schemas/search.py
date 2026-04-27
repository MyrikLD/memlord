from pydantic import BaseModel

from .memory_type import MemoryType


class SearchResult(BaseModel):
    id: int
    name: str
    content: str
    memory_type: MemoryType
    rrf_score: float
    vec_similarity: float | None
    workspace: str | None = None
