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


async def test_create_api_key_ui_shows_modal(api_client, session, user_id):
    r = await api_client.post("/ui/account/api-keys", data={"name": "laptop"})
    assert r.status_code == 200
    html = r.text
    assert "API key created" in html  # modal header
    assert "mk_" in html  # raw key surfaced once
    assert 'x-ref="key"' in html  # copy target
    assert ">Copy<" in html  # copy button

    keys = await ApiKeyDao(session).list_for_user(user_id)
    assert [k.name for k in keys] == ["laptop"]

    # On a normal load the raw key (and its modal) must NOT appear.
    page = await api_client.get("/ui/account")
    assert page.status_code == 200
    assert keys[0].prefix in page.text  # listed by prefix
    assert "API key created" not in page.text


async def test_create_api_key_ui_rejects_duplicate_name(api_client, session, user_id):
    ok = await api_client.post("/ui/account/api-keys", data={"name": "dup"})
    assert ok.status_code == 200

    dup = await api_client.post("/ui/account/api-keys", data={"name": "dup"})
    assert dup.status_code == 400
    assert "already exists" in dup.text
    # The failed attempt must not have created a second row.
    assert len(await ApiKeyDao(session).list_for_user(user_id)) == 1


async def test_delete_api_key_ui(api_client, session, user_id):
    await api_client.post("/ui/account/api-keys", data={"name": "ci"})
    key_id = (await ApiKeyDao(session).list_for_user(user_id))[0].id

    r = await api_client.delete(f"/ui/account/api-keys/{key_id}")
    assert r.status_code == 204
    assert await ApiKeyDao(session).list_for_user(user_id) == []
