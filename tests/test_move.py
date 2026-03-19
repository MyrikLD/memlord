import pytest

from mnemos.auth import hash_password
from mnemos.dao import MemoryDao
from mnemos.dao.user import UserDao
from mnemos.dao.workspace import WorkspaceDao
from mnemos.schemas import MemoryType


@pytest.fixture
async def other_workspace_id(session, user_id: int) -> int:
    ws = await WorkspaceDao(session).create(name="other", owner_id=user_id)
    return ws.id


@pytest.fixture
async def memory_id(session, user_id: int, workspace_id: int) -> int:
    mid, _ = await MemoryDao(session, user_id).create(
        content="move me",
        memory_type=MemoryType.fact,
        metadata={},
        tags=["x"],
        workspace_id=workspace_id,
    )
    return mid


async def test_move_changes_workspace(
    session, user_id, workspace_id, other_workspace_id, memory_id
):
    dao = MemoryDao(session, user_id)
    await dao.move(memory_id, other_workspace_id)

    mem = await dao.get(memory_id)
    assert mem is not None
    assert mem.workspace_id == other_workspace_id


async def test_move_not_found(session, user_id, other_workspace_id):
    dao = MemoryDao(session, user_id)
    with pytest.raises(ValueError, match="not found"):
        await dao.move(999999, other_workspace_id)


async def test_move_inaccessible_workspace_raises(session, user_id, memory_id):
    other_user = await UserDao(session).create(
        email="other@example.com",
        display_name="Other User",
        hashed_password=hash_password("pass"),
    )
    other_ws = await WorkspaceDao(session).get_personal(other_user.id)

    dao = MemoryDao(session, user_id)
    with pytest.raises(PermissionError, match="No access"):
        await dao.move(memory_id, other_ws.id)


async def test_move_duplicate_content_raises(
    session, user_id, workspace_id, other_workspace_id, memory_id
):
    dao = MemoryDao(session, user_id)
    # create the same content in the target workspace
    await dao.create(
        content="move me",
        memory_type=MemoryType.fact,
        metadata={},
        tags=[],
        workspace_id=other_workspace_id,
    )
    with pytest.raises(ValueError, match="already exists"):
        await dao.move(memory_id, other_workspace_id)
