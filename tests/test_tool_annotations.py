from memlord.server import mcp

HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


async def test_every_tool_declares_all_hints():
    tools = await mcp.list_tools()
    assert tools

    missing = {}
    for tool in tools:
        wire = tool.to_mcp_tool().model_dump(by_alias=True, mode="json")
        annotations = wire["annotations"] or {}
        absent = [h for h in HINTS if not isinstance(annotations.get(h), bool)]
        if absent:
            missing[tool.name] = absent
    assert missing == {}
