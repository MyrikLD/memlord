from pydantic import BaseModel

from memlord.schemas.pagination import Paginated


class MemoriesFilter(BaseModel):
    page: int = 1
    page_size: int = 20
    memory_type: str | None = None
    tag: str = ""
    workspace: str = ""


class WorkspaceSimple(BaseModel):
    id: int
    name: str
    is_personal: bool


class MemoryItem(BaseModel):
    id: int
    name: str
    content: str
    memory_type: str | None
    created_at: str
    workspace_id: int | None
    workspace_name: str | None
    tags: list[str]


class MemoryDetail(BaseModel):
    id: int
    name: str
    content: str
    memory_type: str | None
    created_at: str
    workspace_id: int | None
    workspace_name: str | None
    tags: list[str]
    metadata: dict | None
    writable_workspaces: list[WorkspaceSimple]


class MemoriesResponse(Paginated[MemoryItem]): ...


class MoveRequest(BaseModel):
    to_workspace_id: int
