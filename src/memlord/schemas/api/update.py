from datetime import datetime

from ..base import Schema
from ..memory_type import MemoryType


class UpdateMemoryRequest(Schema):
    content: str | None = None
    name: str | None = None
    memory_type: MemoryType | None = None
    tags: set[str] | None = None
    metadata: dict | None = None
    expires_at: datetime | None = None
