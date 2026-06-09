from datetime import datetime

from pydantic import BaseModel


class ApiKeyInfo(BaseModel):
    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None


class ApiKeyCreated(BaseModel):
    raw: str
