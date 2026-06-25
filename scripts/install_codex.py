#!/usr/bin/env python3
"""One-command Eddy bootstrap for Codex.

Run from a cloned Eddy repo. It makes Eddy visible to Codex in the two ways Codex can actually use
today: a skill (`~/.codex/skills/eddy`) plus an MCP server (`~/.codex/config.toml`). It does not
publish packages, upload videos, or mutate source footage.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WRAPPER_DIR = Path.home() / ".eddy" / "bin"
WRAPPER = WRAPPER_DIR / "eddy-mcp"


def _python_version(command: str) -> tuple[int, int] | None:
    try:
        out = subprocess.check_output(
            [command, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None
    try:
        major, minor = out.split(".", 1)
        return int(major), int(minor)
    except ValueError:
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _recommended_python() -> tuple[str, str | None]:
    """Prefer a stable Eddy Python over whatever `python3` currently aliases to."""
    override = os.environ.get("EDDY_INSTALL_PYTHON")
    candidates = _dedupe([override or "", "python3.12", "python3.11", sys.executable, "python3"])
    fallback: tuple[str, str | None] | None = None
    for command in candidates:
        version = _python_version(command)
        if version is None:
            continue
        major, minor = version
        if major == 3 and 11 <= minor <= 12:
            return _resolve_executable(command), None
        if major == 3 and minor >= 11 and fallback is None:
            fallback = (
                _resolve_executable(command),
                f"using Python {major}.{minor}; Python 3.11-3.12 is preferred for video/audio wheels",
            )
    if fallback:
        return fallback
    raise RuntimeError("Eddy needs Python 3.11+. Install Python 3.12 or 3.11, then rerun this installer.")


def _resolve_executable(command: str) -> str:
    if "/" in command:
        return command
    return shutil.which(command) or command


def _load_repo_modules() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(SRC))


def _cmd_str(cmd: list[str]) -> str:
    return " ".join(json.dumps(part) if " " in part else part for part in cmd)


def _run(cmd: list[str], *, dry_run: bool, steps: list[dict[str, Any]]) -> None:
    steps.append({"type": "command", "command": cmd, "display": _cmd_str(cmd), "dry_run": dry_run})
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def _write_mcp_wrapper(*, python: str, dry_run: bool) -> dict[str, Any]:
    body = f"""#!/bin/sh
exec "{python}" -m eddy.mcp_server.server "$@"
"""
    result = {"path": str(WRAPPER), "python": python, "dry_run": dry_run}
    if dry_run:
        result["content_preview"] = body
        return result
    WRAPPER_DIR.mkdir(parents=True, exist_ok=True)
    WRAPPER.write_text(body)
    WRAPPER.chmod(WRAPPER.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    result["action"] = "written"
    return result


def _install_skill(*, copy: bool, dry_run: bool) -> list[dict[str, str]]:
    from install_agent_skill import _candidate_skill_dirs, install

    if dry_run:
        return [{"target": str(path / "eddy"), "action": "would_install"} for path in _candidate_skill_dirs("codex")]
    return install("codex", copy=copy)


def _install_mcp(*, command: str, dry_run: bool) -> dict[str, Any]:
    from eddy.mcp_server.install import install

    try:
        return install("codex", command=command, dry_run=dry_run)
    except ModuleNotFoundError as exc:
        if not dry_run or exc.name != "tomlkit":
            raise
        return {
            "client": "codex",
            "path": str(Path.home() / ".codex" / "config.toml"),
            "command": command,
            "dry_run": True,
            "action": "preview",
            "content_preview": f'[mcp_servers.eddy]\ncommand = "{command}"\nargs = []\n',
            "warning": "tomlkit is not installed yet; this is a simple preview before pip install.",
        }


def _verify(*, python: str, dry_run: bool, steps: list[dict[str, Any]]) -> None:
    checks = [
        [python, "-m", "eddy.cli", "--version"],
        [python, "-m", "eddy.cli", "mcp", "install", "--client", "codex", "--dry-run", "--command", str(WRAPPER)],
        [python, "-m", "eddy.cli", "bootstrap", "--json"],
    ]
    for cmd in checks:
        try:
            _run(cmd, dry_run=dry_run, steps=steps)
        except subprocess.CalledProcessError as exc:
            steps.append({"type": "verification_warning", "command": cmd, "returncode": exc.returncode})


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Eddy into Codex as a skill plus MCP server.")
    parser.add_argument("--copy", action="store_true", help="Copy the repo into ~/.codex/skills instead of symlinking.")
    parser.add_argument("--dry-run", action="store_true", help="Preview all writes and commands.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    parser.add_argument("--skip-python-install", action="store_true", help="Skip `pip install -e .[mcp]`.")
    parser.add_argument(
        "--skip-studio-sound",
        action="store_true",
        help="Skip provisioning the heavy local Studio Sound backend. The edit gate will block until installed.",
    )
    parser.add_argument("--skip-mcp", action="store_true", help="Install the skill only; do not write Codex MCP config.")
    args = parser.parse_args()

    _load_repo_modules()
    python, python_warning = _recommended_python()
    steps: list[dict[str, Any]] = []

    skill_results = _install_skill(copy=args.copy, dry_run=args.dry_run)

    if not args.skip_python_install:
        _run([python, "-m", "pip", "install", "-e", f"{ROOT}[mcp]"], dry_run=args.dry_run, steps=steps)
        if not args.skip_studio_sound:
            _run([python, "-m", "eddy.cli", "studio-sound", "install"], dry_run=args.dry_run, steps=steps)

    wrapper = _write_mcp_wrapper(python=python, dry_run=args.dry_run)
    mcp_result: dict[str, Any] | None = None
    if not args.skip_mcp:
        mcp_result = _install_mcp(command=str(WRAPPER), dry_run=args.dry_run)

    if not args.skip_python_install:
        _verify(python=python, dry_run=args.dry_run, steps=steps)

    out = {
        "status": "preview" if args.dry_run else "installed",
        "repo": str(ROOT),
        "python": python,
        "python_warning": python_warning,
        "codex_skill": skill_results,
        "python_install": not args.skip_python_install,
        "studio_sound_install": bool(not args.skip_python_install and not args.skip_studio_sound),
        "mcp_wrapper": wrapper,
        "codex_mcp": mcp_result,
        "steps": steps,
        "next_user_prompt": "Use Eddy to edit this footage.",
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    print(f"Eddy Codex bootstrap: {out['status']}")
    for item in skill_results:
        print(f"skill {item['action']}: {item['target']}")
    if mcp_result:
        print(f"mcp {mcp_result['action']}: {mcp_result['path']} -> {mcp_result['command']}")
    print("Next: restart/reload Codex tools if needed, then ask: Use Eddy to edit this footage.")


if __name__ == "__main__":
    main()
