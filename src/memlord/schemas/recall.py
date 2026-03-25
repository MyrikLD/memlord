from pydantic import BaseModel

from .memory_type import MemoryType


class RecallResult(BaseModel):
    id: int
    content: str
    memory_type: MemoryType | None
    tags: set[str]
    created_at: str
    workspace_id: int | None = None
