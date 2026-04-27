import json


async def test_pipeline(api_client, workspace_id):
    # seed a memory via MCP is not available here, so use the fact that
    # the MCP store endpoint exists — instead we verify the REST layer directly
    # by relying on another fixture workspace to test move.

    # nothing stored yet
    resp = await api_client.post("/api/memories", json={})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # --- store via MCP tool is out of scope; seed via import ---

    items = [
        {
            "content": "rest pipeline memory",
            "memory_type": "fact",
            "tags": ["rest", "pipeline"],
            "metadata": {},
        }
    ]
    resp = await api_client.post(
        f"/api/workspaces/{workspace_id}/import",
        files={"file": ("m.json", json.dumps(items).encode(), "application/json")},
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1

    # --- list ---
    resp = await api_client.post("/api/memories", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    mem = body["items"][0]
    mid = mem["id"]
    assert mem["content"] == "rest pipeline memory"
    assert mem["memory_type"] == "fact"
    assert sorted(mem["tags"]) == ["pipeline", "rest"]

    # --- list with filters ---
    resp = await api_client.post("/api/memories", json={"memory_type": "fact"})
    assert resp.json()["total"] == 1

    resp = await api_client.post("/api/memories", json={"memory_type": "preference"})
    assert resp.json()["total"] == 0

    resp = await api_client.post("/api/memories", json={"tag": "rest"})
    assert resp.json()["total"] == 1

    resp = await api_client.post("/api/memories", json={"tag": "nope"})
    assert resp.json()["total"] == 0

    # --- get ---
    resp = await api_client.get(f"/api/memories/{workspace_id}/{mid}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["content"] == "rest pipeline memory"
    assert not detail["metadata"]
    assert sorted(detail["tags"]) == ["pipeline", "rest"]

    # --- update ---
    resp = await api_client.put(
        f"/api/memories/{workspace_id}/{mid}",
        json={
            "content": "updated rest memory",
            "memory_type": "preference",
            "tags": ["rest", "updated"],
            "metadata": {"v": 1},
        },
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["content"] == "updated rest memory"
    assert updated["memory_type"] == "preference"
    assert sorted(updated["tags"]) == ["rest", "updated"]
    assert updated["metadata"] == {"v": 1}

    # --- search ---
    resp = await api_client.get("/api/search?q=updated+rest+memory")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert any(r["id"] == mid for r in results)

    # --- delete ---
    resp = await api_client.delete(f"/api/memories/{workspace_id}/{mid}")
    assert resp.status_code == 204

    resp = await api_client.get(f"/api/memories/{workspace_id}/{mid}")
    assert resp.status_code == 404


async def test_workspace_pipeline(api_client):
    # --- create ---
    resp = await api_client.post("/api/workspaces", json={"name": "Test WS", "description": "desc"})
    assert resp.status_code == 201
    ws = resp.json()
    ws_id = ws["id"]
    assert ws["name"] == "Test WS"
    assert ws["role"] == "owner"

    # --- list ---
    resp = await api_client.get("/api/workspaces")
    names = [w["name"] for w in resp.json()]
    assert "Test WS" in names

    # --- get ---
    resp = await api_client.get(f"/api/workspaces/{ws_id}")
    assert resp.status_code == 200
    assert resp.json()["workspace"]["name"] == "Test WS"
    assert len(resp.json()["members"]) == 1

    # --- rename ---
    resp = await api_client.put(f"/api/workspaces/{ws_id}/rename", json={"name": "Renamed WS"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed WS"

    # --- description ---
    resp = await api_client.put(
        f"/api/workspaces/{ws_id}/description", json={"description": "new desc"}
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "new desc"

    # --- delete ---
    resp = await api_client.delete(f"/api/workspaces/{ws_id}")
    assert resp.status_code == 204

    resp = await api_client.get(f"/api/workspaces/{ws_id}")
    assert resp.status_code == 404


async def test_workspace_duplicate_name(api_client):
    resp = await api_client.post("/api/workspaces", json={"name": "Dup WS"})
    assert resp.status_code == 201

    resp = await api_client.post("/api/workspaces", json={"name": "Dup WS"})
    assert resp.status_code == 409
