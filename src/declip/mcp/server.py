"""Declip MCP Server — declarative video editing tools for Claude."""

import sys
import logging

from mcp.server.fastmcp import FastMCP

# All logging to stderr (MCP uses stdio for transport)
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

mcp = FastMCP("declip")

# Register all tool modules
from declip.mcp import (
    project_tools, quick_tools, analysis_tools, media_tools,
    advanced_tools, generate_tools, edit_tools, pipeline_tools,
    workflow_tools,
)

project_tools.register(mcp)
quick_tools.register(mcp)
analysis_tools.register(mcp)
media_tools.register(mcp)
advanced_tools.register(mcp)
generate_tools.register(mcp)
edit_tools.register(mcp)
pipeline_tools.register(mcp)
workflow_tools.register(mcp)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
