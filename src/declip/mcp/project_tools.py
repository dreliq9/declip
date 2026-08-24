"""MCP adapter for Declip project operations."""
from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP
from declip import project_ops


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def declip_init(directory: str) -> str:
        """Create a minimal Declip project.json template in a directory."""
        return project_ops.init_project(directory)

    @mcp.tool()
    def declip_validate(project_file: str) -> str:
        """Validate project schema and referenced asset existence."""
        return project_ops.validate_project(project_file)

    @mcp.tool()
    def declip_render(project_file: str, backend: str = "auto", output_path: str | None = None, preset: str | None = None, variables: str | None = None) -> str:
        """Render a Declip project with automatic or forced backend selection."""
        try:
            parsed_variables = json.loads(variables) if variables else None
        except json.JSONDecodeError as exc:
            return f"Error: invalid variables JSON: {exc}"
        if parsed_variables is not None and not isinstance(parsed_variables, dict):
            return "Error: variables must decode to a JSON object"
        return project_ops.render_project_file(project_file, backend, output_path, preset, parsed_variables)

    @mcp.tool()
    def declip_export_mlt(project_file: str) -> str:
        """Compile a Declip project to MLT XML without rendering."""
        return project_ops.export_mlt(project_file)

    @mcp.tool()
    def declip_list_presets() -> str:
        """List available output presets."""
        return project_ops.list_presets()

    @mcp.tool()
    def declip_assets(project_file: str) -> str:
        """List referenced project assets with existence, duration, and size."""
        return project_ops.assets(project_file)
