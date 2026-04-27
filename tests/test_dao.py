import pytest

from memlord.dao import MemoryDao
from memlord.schemas import MemoryType


async def test_crud(session, user_id, workspace_id):
    dao = MemoryDao(session, user_id)

    # create
    mid, created = await dao.create(
        content="hello world",
        memory_type=MemoryType.fact,
        metadata={"k": "v"},
        tags={"foo", "bar"},
        name="hello world",
        workspace_id=workspace_id,
    )
    assert created is True
    assert mid > 0

    # idempotent create (same user, same content, same workspace)
    mid2, created2 = await dao.create(
        content="hello world",
        memory_type=MemoryType.fact,
        metadata={},
        tags=set(),
        name="hello world",
        workspace_id=workspace_id,
    )
    assert created2 is False
    assert mid2 == mid

    # fetch_tags
    tags = await dao.fetch_tags([mid])
    assert sorted(tags[mid]) == ["bar", "foo"]

    # fetch_metadata
    meta = await dao.fetch_metadata([mid])
    assert meta[mid][0] == {"k": "v"}

    # update content + tags
    await dao.update(id=mid, workspace_id=workspace_id, content="updated content", tags={"baz"})
    tags2 = await dao.fetch_tags([mid])
    assert tags2[mid] == {"baz"}

    # delete
    await dao.delete(mid, workspace_id=workspace_id)
    with pytest.raises(ValueError):
        await dao.delete(mid, workspace_id=workspace_id)
