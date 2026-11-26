from dataclasses import dataclass
from enum import StrEnum


class WorkspaceGrant(StrEnum):
    read = "read"
    write = "write"


@dataclass(frozen=True)
class Principal:
    user_id: int
    # None means the account's usual permissions. An empty mapping grants nothing.
    grants: dict[int, WorkspaceGrant] | None = None
