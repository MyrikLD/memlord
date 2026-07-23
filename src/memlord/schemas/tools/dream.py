from datetime import UTC, datetime

from pydantic import Field, NaiveDatetime, field_serializer

from ..base import Schema
from ..memory_type import MemoryType


class SimilarPair(Schema):
    name_a: str
    type_a: MemoryType | None
    created_at_a: NaiveDatetime
    name_b: str
    type_b: MemoryType | None
    created_at_b: NaiveDatetime
    workspace: str
    similarity: float = Field(description="Cosine similarity of the two embeddings, 0..1")

    @field_serializer("created_at_a", "created_at_b")
    def serialize_created_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()


class ExpiryItem(Schema):
    name: str
    memory_type: MemoryType | None
    workspace: str
    expires_at: NaiveDatetime

    @field_serializer("expires_at")
    def serialize_expires_at(self, v: datetime) -> str:
        return v.replace(tzinfo=UTC).isoformat()


class DreamReport(Schema):
    similar_pairs: list[SimilarPair] = Field(
        default_factory=list,
        description="Pairs of semantically close memories within one workspace, "
        "candidates for merge/supersession review.",
    )
    expired: list[ExpiryItem] = Field(
        default_factory=list,
        description="Already-expired memories, hidden from reads but not yet purged.",
    )
    expiring_soon: list[ExpiryItem] = Field(
        default_factory=list,
        description="Memories expiring within the next 7 days; extend expires_at if still valuable.",
    )
