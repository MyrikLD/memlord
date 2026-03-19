from datetime import datetime

from pydantic import BaseModel, Field

from .memory_type import MemoryType


class MemoryListItem(BaseModel):
    id: int
    content: str
    memory_type: MemoryType
    metadata: dict = Field(default_factory=dict)
    tags: list[str]
    created_at: datetime
    workspace_id: int | None = None


class MemoryPage(BaseModel):
    items: list[MemoryListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
