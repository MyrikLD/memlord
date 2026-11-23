from pydantic import Field

from .base import Schema


class TagGroup(Schema):
    id: int
    name: str
    aliases: list[str] = Field(default_factory=list)
    memory_count: int


class TagMergeRequest(Schema):
    source: str
    target: str


class TagDetachRequest(Schema):
    alias: str


class TagAlias(Schema):
    """Export/import form of one alias edge in a workspace's tag dictionary."""

    alias: str
    canonical: str
