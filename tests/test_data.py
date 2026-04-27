import json


async def test_export_import(api_client, workspace_id):
    items = [
        {
            "content": "imported fact",
            "memory_type": "fact",
            "name": "imported fact",
            "tags": ["x"],
            "metadata": {},
        },
        {
            "content": "imported pref",
            "memory_type": "preference",
            "name": "imported pref",
            "tags": [],
            "metadata": {"n": 1},
        },
    ]
    resp = await api_client.post(
        f"/api/workspaces/{workspace_id}/import",
        files={"file": ("m.json", json.dumps(items).encode(), "application/json")},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["imported"] == 2
    assert result["skipped"] == 0

    resp = await api_client.get(f"/api/workspaces/{workspace_id}/export")
    assert resp.status_code == 200
    data = resp.json()
    for i in data:
        del i["created_at"]
    assert items == data
