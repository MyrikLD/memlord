from datetime import datetime

from pydantic import BaseModel, Field

from .memory_type import MemoryType
from ..utils.dt import utcnow


class ImportItem(BaseModel):
    content: str
    memory_type: MemoryType
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class StoreResult(BaseModel):
    id: int
    created: bool
