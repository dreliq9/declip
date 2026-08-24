"""Backward-compatible import shim for the Declip CLI.

The command implementation lives in :mod:`declip.cli_adapter` so the CLI remains
an adapter over reusable core capabilities rather than an alternate media engine.
"""

from declip.cli_adapter import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
