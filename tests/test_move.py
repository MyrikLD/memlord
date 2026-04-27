import pytest

from memlord.auth import hash_password
from memlord.dao import MemoryDao
from memlord.dao.user import UserDao
from memlord.dao.workspace import WorkspaceDao
from memlord.schemas import MemoryType


@pytest.fixture
async def other_workspace_id(session, user_id: int) -> int:
    ws = await WorkspaceDao(session, user_id).create(name="other")
    return ws.id


@pytest.fixture
async def memory_id(session, user_id: int, workspace_id: int) -> int:
    mid, _ = await MemoryDao(session, user_id).create(
        content="move me",
        memory_type=MemoryType.fact,
        metadata={},
        tags={"x"},
        name="move me",
        workspace_id=workspace_id,
    )
    return mid


async def test_move_changes_workspace(
    session, user_id, workspace_id, other_workspace_id, memory_id
):
    dao = MemoryDao(session, user_id)
    await dao.move(memory_id, workspace_id, other_workspace_id)

    mem = await dao.get(id=memory_id, workspace_id=other_workspace_id)
    assert mem is not None
    assert mem.workspace_id == other_workspace_id


async def test_move_inaccessible_workspace_raises(session, user_id, memory_id, workspace_id):
    other_user = await UserDao(session).create(
        email="other@example.com",
        display_name="Other User",
        hashed_password=hash_password("pass"),
    )
    other_ws = await WorkspaceDao(session, other_user.id).get_personal()

    dao = MemoryDao(session, user_id)
    with pytest.raises(PermissionError, match="No access"):
        await dao.move(memory_id, workspace_id, other_ws.id)


async def test_move_duplicate_content_raises(
    session, user_id, workspace_id, other_workspace_id, memory_id
):
    dao = MemoryDao(session, user_id)
    # create the same content in the target workspace
    await dao.create(
        content="move me",
        memory_type=MemoryType.fact,
        metadata={},
        tags=set(),
        name="move me",
        workspace_id=other_workspace_id,
    )
    with pytest.raises(ValueError, match="already exists"):
        await dao.move(memory_id, workspace_id, other_workspace_id)
