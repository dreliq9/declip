"""Structured CLI output — human and JSON modes."""

from __future__ import annotations

import io
import json
import sys
import time
from dataclasses import dataclass, field


@dataclass
class OutputManager:
    """Handles both human-readable and NDJSON output.

    When `quiet=True`, all output goes to an internal buffer instead of stdout/stderr.
    Use this in MCP context to prevent stdout writes from corrupting the JSON-RPC transport.
    """
    json_mode: bool = False
    quiet: bool = False
    _events: list[dict] = field(default_factory=list)
    _start: float = field(default_factory=time.time)
    _buffer: io.StringIO = field(default_factory=io.StringIO)

    def _out(self, text: str, file=None):
        """Write text to the appropriate destination."""
        if self.quiet:
            self._buffer.write(text + "\n")
        else:
            print(text, file=file, flush=True)

    def emit(self, stage: str, message: str = "", **data):
        """Emit a status event."""
        event = {"stage": stage, "elapsed_ms": int((time.time() - self._start) * 1000), **data}
        self._events.append(event)

        if self.json_mode:
            self._out(json.dumps(event))
        else:
            if message:
                self._out(message)

    def error(self, stage: str, message: str, **data):
        """Emit an error."""
        event = {"stage": stage, "error": message, **data}
        self._events.append(event)

        if self.quiet:
            self._buffer.write(f"Error: {message}\n")
        elif self.json_mode:
            print(json.dumps(event), file=sys.stderr, flush=True)
        else:
            print(f"Error: {message}", file=sys.stderr, flush=True)

    def progress(self, pct: float, stage: str = "render"):
        """Emit a progress update (0.0 to 1.0)."""
        if self.quiet:
            return  # Skip progress in quiet mode
        if self.json_mode:
            print(json.dumps({"stage": stage, "progress": round(pct, 3)}), flush=True)
        else:
            bar_len = 30
            filled = int(bar_len * pct)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\r  [{bar}] {pct*100:.0f}%", end="", flush=True)
            if pct >= 1.0:
                print()

    def get_log(self) -> str:
        """Get buffered output (for quiet mode). Returns empty string if not quiet."""
        return self._buffer.getvalue()
