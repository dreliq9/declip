import asyncio

from mcp.server import MCPServer

from declip.mcp import server


def test_server_uses_mcp_v2_high_level_server():
    assert isinstance(server.mcp, MCPServer)


def test_server_advertises_and_calls_existing_tools():
    tools = asyncio.run(server.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert {"declip_init", "declip_project_from_clip_plan", "declip_render", "declip_workflow_review"} <= names

    result = asyncio.run(server.mcp.call_tool("declip_list_presets", {}))
    assert result.is_error is False
