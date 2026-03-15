import pytest

from mnemos.dao import MemoryDao


async def test_crud(session):
    dao = MemoryDao(session)

    # create
    mid, created_at, created = await dao.create(
        content="hello world",
        memory_type="observation",
        metadata={"k": "v"},
        client_hostname=None,
        tags=["foo", "bar"],
    )
    assert created is True
    assert mid > 0

    # idempotent create
    mid2, _, created2 = await dao.create(
        content="hello world",
        memory_type=None,
        metadata=None,
        client_hostname=None,
        tags=[],
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
    await dao.update(id=mid, content="updated content", tags=["baz"])
    tags2 = await dao.fetch_tags([mid])
    assert tags2[mid] == ["baz"]

    # delete
    await dao.delete(mid)
    with pytest.raises(ValueError):
        await dao.delete(mid)
