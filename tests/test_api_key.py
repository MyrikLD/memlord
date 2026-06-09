from memlord.auth import hash_password
from memlord.dao.api_key import ApiKeyDao
from memlord.dao.user import UserDao


async def test_api_key_create_and_resolve(session, user_id):
    dao = ApiKeyDao(session)
    raw, info = await dao.create(user_id, "laptop")

    assert raw.startswith("mk_")
    assert raw.startswith(info.prefix)
    assert info.name == "laptop"

    assert await dao.resolve_user(raw) == user_id
    assert await dao.resolve_user("mk_unknown-token") is None

    keys = await dao.list_for_user(user_id)
    assert [k.id for k in keys] == [info.id]


async def test_api_key_delete_is_user_scoped(session, user_id):
    dao = ApiKeyDao(session)
    raw, info = await dao.create(user_id, "ci")

    other = await UserDao(session).create(
        email="other@example.com",
        display_name="Other",
        hashed_password=hash_password("pw"),
    )

    await dao.delete(other.id, info.id)  # чужой не удалит
    assert await dao.resolve_user(raw) == user_id

    await dao.delete(user_id, info.id)  # владелец удалит
    assert await dao.resolve_user(raw) is None


async def test_delete_account_cascades_api_keys(session, user_id):
    dao = ApiKeyDao(session)
    raw, _ = await dao.create(user_id, "key")
    assert await dao.resolve_user(raw) == user_id

    await UserDao(session).delete_account(user_id)

    assert await dao.resolve_user(raw) is None  # ушёл по каскаду
