from .base import Schema
from .memory_type import MemoryType


class SearchResult(Schema):
    id: int
    name: str
    content: str
    memory_type: MemoryType
    rrf_score: float
    vec_similarity: float | None
    workspace: str | None = None
    workspace_id: int | None = None
