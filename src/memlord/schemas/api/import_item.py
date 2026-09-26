from datetime import datetime

from pydantic import Field, model_validator

from memlord.utils.dt import utcnow

from ..base import Schema
from ..memory_type import MemoryType
from ..tag import TagAlias


class ImportItem(Schema):
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


class ExportFile(Schema):
    """Workspace export: memories plus the alias edges of its tag dictionary."""

    memories: list[ImportItem]
    tag_aliases: list[TagAlias] = Field(default_factory=list)


class ImportResult(Schema):
    imported: int
    skipped: int
    aliases_applied: int = 0
