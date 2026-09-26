import json

import pytest
from sqlalchemy import func, select

from memlord.dao import MemoryDao, TagDao
from memlord.dao.workspace import WorkspaceDao
from memlord.models import MemoryTag, Tag
from memlord.schemas import MemoryType
from memlord.tags import normalize_tag


async def _store(session, uid, ws, name, tags):
    mid, _ = await MemoryDao(session, uid).create(
        content=f"memory {name}",
        memory_type=MemoryType.fact,
        metadata={},
        tags=set(tags),
        name=name,
        workspace_id=ws,
        force=True,
    )
    return mid


async def _link_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(MemoryTag)) or 0


async def _by_tag(mcp_client, tags, operation="AND") -> set[str]:
    res = await mcp_client.call_tool("search_by_tag", {"tags": list(tags), "operation": operation})
    return {i.name for i in res.data.items}


async def _by_list(mcp_client, tag) -> set[str]:
    res = await mcp_client.call_tool("list_memories", {"tag": tag})
    return {i.name for i in res.data.items}


@pytest.fixture
async def other_workspace_id(session, user_id: int) -> int:
    ws = await WorkspaceDao(session, user_id).create(name="other")
    return ws.id


# --- normalization ---------------------------------------------------------


def test_normalize_tag_folds_case_space_and_unicode():
    assert normalize_tag("  Dima ") == "dima"
    assert normalize_tag("Дмитрий\u00a0 Иванов") == "дмитрий иванов"
    assert normalize_tag("ﬁle") == "file"
    assert normalize_tag("Straße") == "strasse"


async def test_spelling_variants_collapse_on_store(session, user_id, workspace_id):
    await _store(session, user_id, workspace_id, "m1", {"дима"})
    await _store(session, user_id, workspace_id, "m2", {" ДИМА "})
    names = (await session.scalars(select(Tag.name).where(Tag.workspace_id == workspace_id))).all()
    assert names == ["дима"]


# --- workspace scoping -----------------------------------------------------


async def test_same_name_in_different_workspaces_is_independent(
    session, user_id, workspace_id, other_workspace_id
):
    await _store(session, user_id, workspace_id, "a", {"dima", "дима"})
    await _store(session, user_id, other_workspace_id, "b", {"dima", "дима"})

    dao = TagDao(session, user_id)
    await dao.merge(workspace_id, "дима", "dima")

    assert [g.name for g in await dao.list_groups(workspace_id)] == ["dima"]
    assert sorted(g.name for g in await dao.list_groups(other_workspace_id)) == ["dima", "дима"]
    assert await dao.aliases(other_workspace_id) == []


# --- search through groups -------------------------------------------------


async def test_alias_and_canonical_search_return_same_set(
    session, user_id, workspace_id, mcp_client
):
    await _store(session, user_id, workspace_id, "lat", {"dima"})
    await _store(session, user_id, workspace_id, "cyr", {"дима"})
    await _store(session, user_id, workspace_id, "full", {"дмитрий", "work"})
    await _store(session, user_id, workspace_id, "none", {"other"})

    assert await _by_tag(mcp_client, {"dima"}) == {"lat"}

    dao = TagDao(session, user_id)
    await dao.merge(workspace_id, "dima", "дмитрий")
    await dao.merge(workspace_id, "дима", "дмитрий")

    expected = {"lat", "cyr", "full"}
    for name in ("dima", "дима", "дмитрий", "Дмитрий "):
        assert await _by_tag(mcp_client, {name}) == expected
        assert await _by_list(mcp_client, name) == expected

    # AND across a group member and an unrelated tag; OR across groups.
    assert await _by_tag(mcp_client, {"dima", "work"}) == {"full"}
    assert await _by_tag(mcp_client, {"dima", "other"}, "OR") == {"lat", "cyr", "full", "none"}
    # Two spellings of the same group count as two satisfied names.
    assert await _by_tag(mcp_client, {"dima", "дима"}) == expected


async def test_fulltext_search_matches_aliases(session, user_id, workspace_id, mcp_client):
    await _store(session, user_id, workspace_id, "cyr", {"дима"})
    await _store(session, user_id, workspace_id, "lat", {"dima"})
    res = await mcp_client.call_tool("retrieve_memory", {"query": "dima", "limit": 5})
    assert "cyr" not in {i.name for i in res.data}

    await TagDao(session, user_id).merge(workspace_id, "дима", "dima")
    res = await mcp_client.call_tool("retrieve_memory", {"query": "dima", "limit": 5})
    assert {"cyr", "lat"} <= {i.name for i in res.data}


async def test_outputs_report_canonical_name(
    session, user_id, workspace_id, api_client, mcp_client
):
    mid = await _store(session, user_id, workspace_id, "cyr", {"дима", "x"})
    await _store(session, user_id, workspace_id, "lat", {"dima"})
    await TagDao(session, user_id).merge(workspace_id, "дима", "dima")

    resp = await api_client.get(f"/api/memories/{workspace_id}/{mid}")
    assert resp.json()["tags"] == ["dima", "x"]
    res = await mcp_client.call_tool("get_memory", {"name": "cyr"})
    assert res.data.tags == {"dima", "x"}


async def test_detail_exposes_original_tags(session, user_id, workspace_id, api_client):
    mid = await _store(session, user_id, workspace_id, "cyr", {"дима", "x"})
    await _store(session, user_id, workspace_id, "lat", {"dima"})
    await TagDao(session, user_id).merge(workspace_id, "дима", "dima")

    body = (await api_client.get(f"/api/memories/{workspace_id}/{mid}")).json()
    assert body["tags"] == ["dima", "x"]
    assert body["original_tags"] == ["x", "дима"]

    # Resending the originals leaves the links exactly as they were.
    resp = await api_client.put(
        f"/api/memories/{workspace_id}/{mid}", json={"tags": body["original_tags"]}
    )
    assert resp.json()["original_tags"] == ["x", "дима"]


async def test_update_without_tags_keeps_tags(session, user_id, workspace_id, api_client):
    mid = await _store(session, user_id, workspace_id, "cyr", {"дима"})
    resp = await api_client.put(f"/api/memories/{workspace_id}/{mid}", json={"content": "edited"})
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["дима"]
    resp = await api_client.put(f"/api/memories/{workspace_id}/{mid}", json={"tags": []})
    assert resp.json()["tags"] == []


# --- merge / detach invariants -------------------------------------------------


async def test_merge_touches_only_tag_dictionary(session, user_id, workspace_id, mcp_client):
    a = await _store(session, user_id, workspace_id, "a", {"dima", "x"})
    b = await _store(session, user_id, workspace_id, "b", {"дима"})
    both = await _store(session, user_id, workspace_id, "both", {"dima", "дима"})
    links_before = set((await session.execute(select(MemoryTag.memory_id, MemoryTag.tag_id))).all())

    dao = TagDao(session, user_id)
    merged = await dao.merge(workspace_id, "дима", "dima")
    assert (merged.name, merged.aliases, merged.memory_count) == ("dima", ["дима"], 3)
    assert (
        set((await session.execute(select(MemoryTag.memory_id, MemoryTag.tag_id))).all())
        == links_before
    )

    mem_dao = MemoryDao(session, user_id)
    assert await mem_dao.fetch_tags([a, b, both]) == {a: {"dima", "x"}, b: {"dima"}, both: {"dima"}}
    assert await mem_dao.fetch_original_tags([both]) == {both: {"dima", "дима"}}
    assert await _by_tag(mcp_client, {"дима"}) == {"a", "b", "both"}


async def test_detach_undoes_the_merge(session, user_id, workspace_id, mcp_client):
    await _store(session, user_id, workspace_id, "a", {"dima"})
    await _store(session, user_id, workspace_id, "b", {"дима"})
    dao = TagDao(session, user_id)
    before = await _link_count(session)
    await dao.merge(workspace_id, "дима", "dima")
    await _store(session, user_id, workspace_id, "c", {"Дима"})
    assert await _by_tag(mcp_client, {"dima"}) == {"a", "b", "c"}

    group = await dao.detach(workspace_id, "дима")
    assert (group.name, group.aliases, group.memory_count) == ("дима", [], 2)
    assert await _by_tag(mcp_client, {"dima"}) == {"a"}
    assert await _by_tag(mcp_client, {"дима"}) == {"b", "c"}
    assert sorted(g.name for g in await dao.list_groups(workspace_id)) == ["dima", "дима"]
    assert await _link_count(session) == before + 1

    with pytest.raises(ValueError, match="not an alias"):
        await dao.detach(workspace_id, "дима")


async def test_merge_into_alias_yields_flat_group(session, user_id, workspace_id):
    for name, tag in (("a", "dima"), ("b", "дима"), ("c", "дмитрий"), ("d", "dmitry")):
        await _store(session, user_id, workspace_id, name, {tag})
    dao = TagDao(session, user_id)

    await dao.merge(workspace_id, "dima", "дмитрий")  # dima -> дмитрий
    await dao.merge(workspace_id, "dmitry", "дима")  # dmitry -> дима (both roots)
    # Target is an alias: redirected to its canonical; the source's own alias moves too.
    await dao.merge(workspace_id, "дима", "dima")

    groups = await dao.list_groups(workspace_id)
    assert len(groups) == 1
    assert groups[0].name == "дмитрий"
    assert groups[0].aliases == ["dima", "dmitry", "дима"]
    assert groups[0].memory_count == 4
    parents = (
        await session.execute(
            select(Tag.name, Tag.parent_id).where(
                Tag.workspace_id == workspace_id, Tag.parent_id.isnot(None)
            )
        )
    ).all()
    root_id = await session.scalar(
        select(Tag.id).where(Tag.workspace_id == workspace_id, Tag.name == "дмитрий")
    )
    assert all(p == root_id for _, p in parents)

    with pytest.raises(ValueError, match="same group"):
        await dao.merge(workspace_id, "dima", "dmitry")


async def test_merging_an_alias_moves_only_that_alias(session, user_id, workspace_id):
    for name, tag in (("a", "dima"), ("b", "дима"), ("c", "дмитрий"), ("d", "work")):
        await _store(session, user_id, workspace_id, name, {tag})
    dao = TagDao(session, user_id)
    await dao.merge(workspace_id, "dima", "дмитрий")
    await dao.merge(workspace_id, "дима", "дмитрий")

    group = await dao.merge(workspace_id, "dima", "work")
    assert (group.name, group.aliases, group.memory_count) == ("work", ["dima"], 2)
    groups = {g.name: (g.aliases, g.memory_count) for g in await dao.list_groups(workspace_id)}
    assert groups == {"work": (["dima"], 2), "дмитрий": (["дима"], 2)}


async def test_deleting_canonical_memories_keeps_aliases_and_links(
    session, user_id, workspace_id, mcp_client
):
    canon = await _store(session, user_id, workspace_id, "canon", {"dima"})
    await _store(session, user_id, workspace_id, "alias", {"дима"})
    dao = TagDao(session, user_id)
    await dao.merge(workspace_id, "дима", "dima")

    await MemoryDao(session, user_id).delete(canon, workspace_id)

    # The canonical tag has no memories of its own but anchors the group.
    groups = await dao.list_groups(workspace_id)
    assert [(g.name, g.aliases, g.memory_count) for g in groups] == [("dima", ["дима"], 1)]
    assert await _by_tag(mcp_client, {"dima"}) == {"alias"}
    assert await _link_count(session) == 1


async def test_move_keeps_tag_links(session, user_id, workspace_id, other_workspace_id):
    mid = await _store(session, user_id, workspace_id, "m", {"dima", "x"})
    before = await _link_count(session)
    dao = MemoryDao(session, user_id)
    await dao.move(mid, workspace_id, other_workspace_id)
    assert await _link_count(session) == before
    assert (await dao.fetch_tags([mid]))[mid] == {"dima", "x"}


# --- permissions -------------------------------------------------------------


async def test_merge_requires_write_access(session, user_id, workspace_id, api_client):
    await _store(session, user_id, workspace_id, "a", {"dima"})
    await _store(session, user_id, workspace_id, "b", {"дима"})
    resp = await api_client.post(
        f"/api/workspaces/{workspace_id}/tags/merge", json={"source": "дима", "target": "dima"}
    )
    assert resp.status_code == 200

    resp = await api_client.get(f"/api/workspaces/{workspace_id}/tags")
    assert [(g["name"], g["aliases"]) for g in resp.json()] == [("dima", ["дима"])]

    resp = await api_client.post(
        f"/api/workspaces/{workspace_id}/tags/detach", json={"alias": "дима"}
    )
    assert resp.status_code == 200
    assert (resp.json()["name"], resp.json()["aliases"]) == ("дима", [])

    resp = await api_client.post(
        f"/api/workspaces/{workspace_id + 1000}/tags/merge",
        json={"source": "дима", "target": "dima"},
    )
    assert resp.status_code == 403


# --- export / import -----------------------------------------------------------


async def test_export_import_reproduces_groups(
    session, user_id, workspace_id, other_workspace_id, api_client
):
    await _store(session, user_id, workspace_id, "a", {"dima"})
    await _store(session, user_id, workspace_id, "b", {"дима"})
    await _store(session, user_id, workspace_id, "c", {"дмитрий"})
    dao = TagDao(session, user_id)
    await dao.merge(workspace_id, "dima", "дмитрий")
    await dao.merge(workspace_id, "дима", "дмитрий")

    resp = await api_client.get(f"/api/workspaces/{workspace_id}/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tag_aliases"] == [
        {"alias": "dima", "canonical": "дмитрий"},
        {"alias": "дима", "canonical": "дмитрий"},
    ]

    resp = await api_client.post(
        f"/api/workspaces/{other_workspace_id}/import",
        files={"file": ("m.json", json.dumps(data).encode(), "application/json")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"imported": 3, "skipped": 0, "aliases_applied": 2}

    groups = await dao.list_groups(other_workspace_id)
    assert [(g.name, g.aliases, g.memory_count) for g in groups] == [
        ("дмитрий", ["dima", "дима"], 3)
    ]
    assert await dao.aliases(other_workspace_id) == await dao.aliases(workspace_id)
    assert await _link_count(session) == 6
