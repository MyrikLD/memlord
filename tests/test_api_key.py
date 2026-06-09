from memlord.auth import hash_password
from memlord.dao.api_key import ApiKeyDao
from memlord.dao.user import UserDao


async def test_api_key_create_and_resolve(session, user_id):
    dao = ApiKeyDao(session)
    raw = await dao.create(user_id, "laptop")

    assert raw.startswith("mk_")
    assert await dao.resolve_user(raw) == user_id
    assert await dao.resolve_user("mk_unknown-token") is None

    keys = await dao.list_for_user(user_id)
    assert [k.name for k in keys] == ["laptop"]
    assert raw.startswith(keys[0].prefix)


async def test_api_key_delete_is_user_scoped(session, user_id):
    dao = ApiKeyDao(session)
    raw = await dao.create(user_id, "ci")
    key_id = (await dao.list_for_user(user_id))[0].id

    other = await UserDao(session).create(
        email="other@example.com",
        display_name="Other",
        hashed_password=hash_password("pw"),
    )

    await dao.delete(other.id, key_id)  # чужой не удалит
    assert await dao.resolve_user(raw) == user_id

    await dao.delete(user_id, key_id)  # владелец удалит
    assert await dao.resolve_user(raw) is None


async def test_delete_account_cascades_api_keys(session, user_id):
    dao = ApiKeyDao(session)
    raw = await dao.create(user_id, "key")
    assert await dao.resolve_user(raw) == user_id

    await UserDao(session).delete_account(user_id)

    assert await dao.resolve_user(raw) is None  # ушёл по каскаду


async def test_create_api_key_api_returns_raw_once(api_client, session, user_id):
    r = await api_client.post("/api/api-keys", data={"name": "laptop"})
    assert r.status_code == 200
    data = r.json()
    assert data["raw"].startswith("mk_")

    keys = await ApiKeyDao(session).list_for_user(user_id)
    assert [k.name for k in keys] == ["laptop"]

    # The raw secret is returned only by create, never on a normal page load.
    page = await api_client.get("/ui/account")
    assert page.status_code == 200
    assert keys[0].prefix in page.text  # listed by prefix
    assert data["raw"] not in page.text


async def test_create_api_key_api_rejects_duplicate_name(api_client, session, user_id):
    ok = await api_client.post("/api/api-keys", data={"name": "dup"})
    assert ok.status_code == 200

    dup = await api_client.post("/api/api-keys", data={"name": "dup"})
    assert dup.status_code == 400
    assert "already exists" in dup.text
    # The failed attempt must not have created a second row.
    assert len(await ApiKeyDao(session).list_for_user(user_id)) == 1


async def test_delete_api_key_api(api_client, session, user_id):
    await api_client.post("/api/api-keys", data={"name": "ci"})
    key_id = (await ApiKeyDao(session).list_for_user(user_id))[0].id

    r = await api_client.delete(f"/api/api-keys/{key_id}")
    assert r.status_code == 204
    assert await ApiKeyDao(session).list_for_user(user_id) == []


async def test_delete_api_key_api_404_when_missing(api_client):
    r = await api_client.delete("/api/api-keys/999999")
    assert r.status_code == 404
