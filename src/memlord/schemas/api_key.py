from datetime import datetime

from .base import Schema


class ApiKeyInfo(Schema):
    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None


class ApiKeyCreated(Schema):
    raw: str
