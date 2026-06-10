from ..base import Schema


class SearchItem(Schema):
    id: int
    content: str
    memory_type: str | None
    created_at: str
    workspace_id: int | None
    workspace_name: str | None
    tags: list[str]
    rrf_score: float


class SearchResponse(Schema):
    results: list[SearchItem]
    query: str
