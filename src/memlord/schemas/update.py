from pydantic import BaseModel

from .memory_type import MemoryType


class UpdateMemoryRequest(BaseModel):
    content: str | None = None
    memory_type: MemoryType | None = None
    tags: list[str] | None = None
    metadata: dict | None = None
