import ast
import inspect

import declip.cli
import declip.cli_adapter
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


def test_core_capabilities_do_not_depend_on_mcp_or_click():
    for module in (declip.edit, declip.project_ops, declip.quick, declip.pipelines.production):
        imports = _import_roots(module)
        assert "mcp" not in imports
        assert "click" not in imports


def test_thin_adapters_do_not_own_process_execution():
    for module in (
        declip.cli,
        declip.cli_adapter,
        declip.mcp.edit_tools,
        declip.mcp.pipeline_tools,
        declip.mcp.project_tools,
        declip.mcp.quick_tools,
    ):
        imports = _import_roots(module)
        assert "subprocess" not in imports
        assert "tempfile" not in imports


def test_cli_command_surface_is_preserved():
    expected = {
        "validate", "render", "export-mlt", "init", "presets", "assets",
        "trim", "concat", "probe", "thumbnail", "extract-frames",
        "detect-scenes", "detect-silence", "review", "loudness",
        "extract-audio", "detect-beats", "ocr", "audio-to-midi", "streams",
        "contact-sheet", "transcribe", "chapters", "waveform", "duck-filter",
        "export-fcpxml", "batch-render", "watch", "generate", "estimate-cost",
        "models", "loudnorm", "denoise", "sidechain", "speed", "stabilize",
        "reverse", "color-grade", "workflow",
    }
    assert set(declip.cli_adapter.main.commands) == expected
    assert set(declip.cli_adapter.workflow.commands) == {
        "ingest", "cutdown", "speech-cleanup", "beat-sync", "vertical", "review"
    }
