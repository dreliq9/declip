import ast
import inspect

import declip.edit
import declip.project_ops
import declip.quick
import declip.pipelines.production
import declip.mcp.edit_tools
import declip.mcp.pipeline_tools
import declip.mcp.project_tools
import declip.mcp.quick_tools


def _import_roots(module) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_core_capabilities_do_not_depend_on_mcp():
    for module in (declip.edit, declip.project_ops, declip.quick, declip.pipelines.production):
        assert "mcp" not in _import_roots(module)


def test_thin_mcp_adapters_do_not_own_process_execution():
    for module in (
        declip.mcp.edit_tools,
        declip.mcp.pipeline_tools,
        declip.mcp.project_tools,
        declip.mcp.quick_tools,
    ):
        imports = _import_roots(module)
        assert "subprocess" not in imports
        assert "tempfile" not in imports
