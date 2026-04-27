from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from memlord.utils.dt import utcnow

from ..memory_type import MemoryType


class ImportItem(BaseModel):
    content: str
    memory_type: MemoryType
    name: str
    tags: set[str] = Field(default_factory=set)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="before")
    @classmethod
    def fill_name(cls, data: dict) -> dict:
        if not data.get("name"):
            data["name"] = (data.get("content") or "")[:60].strip()
        return data


class ImportResult(BaseModel):
    imported: int
    skipped: int
