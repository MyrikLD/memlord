import json


async def test_export_import(api_client, workspace_id):
    items = [
        {
            "content": "imported fact",
            "memory_type": "fact",
            "tags": ["x"],
            "metadata": {},
        },
        {
            "content": "imported pref",
            "memory_type": "preference",
            "tags": [],
            "metadata": {"n": 1},
        },
    ]
    resp = await api_client.post(
        "/ui/import",
        files={"file": ("m.json", json.dumps(items).encode(), "application/json")},
        data={"workspace_id": str(workspace_id)},
    )
    assert resp.status_code == 303
    assert "imported=2" in resp.headers["location"]

    resp = await api_client.get(f"/ui/export?workspace_id={workspace_id}")
    data = resp.json()
    for i in data:
        del i["created_at"]
    assert items == data
