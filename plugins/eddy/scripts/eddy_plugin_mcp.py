#!/usr/bin/env python3
"""Codex plugin MCP launcher for Eddy."""

from __future__ import annotations

import json
import os
import sys

from eddy_plugin_bootstrap import ensure_latest_stable, home_root, venv_python


def main() -> int:
    result = ensure_latest_stable()
    print(json.dumps({"eddy_plugin_bootstrap": result}, sort_keys=True), file=sys.stderr)
    active_python = venv_python(home_root() / "venv")
    if not active_python.exists():
        print(
            json.dumps(
                {
                    "blocker": "eddy_plugin_active_python_missing",
                    "path": str(active_python),
                    "state": str(home_root() / "plugin-state.json"),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    os.environ["EDDY_PLUGIN_AUTO_UPDATE"] = "1"
    os.execv(str(active_python), [str(active_python), "-m", "eddy.mcp_server.server"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
