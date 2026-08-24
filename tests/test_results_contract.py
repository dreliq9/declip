from declip import results
from declip.mcp import types as mcp_types

def test_mcp_result_imports_are_core_aliases():
    assert mcp_types.ProbeResult is results.ProbeResult
    assert mcp_types.FileResult is results.FileResult
    assert mcp_types.TrimResult is results.TrimResult
    assert mcp_types.ConcatResult is results.ConcatResult
    assert mcp_types.ThumbnailResult is results.ThumbnailResult
