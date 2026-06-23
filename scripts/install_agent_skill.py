#!/usr/bin/env python3
"""Install Eddy's root skill for Codex and/or Claude-style skill folders.

This script intentionally does not write secrets and does not configure publishing. It only makes
the local checkout discoverable to an agent and, optionally, installs Eddy as an editable Python
package for the current interpreter.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _candidate_skill_dirs(agent: str) -> list[Path]:
    home = Path.home()
    dirs: list[Path] = []
    if agent in {"auto", "codex"}:
        dirs.append(home / ".codex" / "skills")
    if agent in {"auto", "claude"}:
        dirs.append(home / ".claude" / "skills")
        dirs.append(home / ".agents" / "skills")
        dirs.append(home / ".claude" / "commands")
    return dirs


def _link_or_copy(target: Path, copy: bool) -> str:
    if target.exists() or target.is_symlink():
        if target.resolve() == ROOT:
            return "exists"
        if target.is_symlink():
            target.unlink()
        else:
            backup = target.with_name(f"{target.name}.backup")
            if backup.exists():
                raise RuntimeError(f"refusing to overwrite existing backup: {backup}")
            target.rename(backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(".git", ".venv", "runs", "work", "build"))
        return "copied"
    target.symlink_to(ROOT, target_is_directory=True)
    return "linked"


def install(agent: str, copy: bool) -> list[dict[str, str]]:
    results = []
    for base in _candidate_skill_dirs(agent):
        # Claude command folders are not skill folders; skip until a dedicated command installer exists.
        if base.name == "commands":
            continue
        target = base / "eddy"
        action = _link_or_copy(target, copy=copy)
        results.append({"target": str(target), "action": action})
    return results


def install_editable(install_studio_sound: bool) -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(ROOT)], check=True)
    if install_studio_sound:
        subprocess.run([sys.executable, "-m", "eddy.cli", "studio-sound", "install"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Eddy for local agent use.")
    parser.add_argument("--agent", choices=["auto", "codex", "claude"], default="auto")
    parser.add_argument("--copy", action="store_true", help="Copy the repo instead of symlinking it.")
    parser.add_argument("--install-editable", action="store_true", help="Also run `pip install -e .`.")
    parser.add_argument(
        "--skip-studio-sound",
        action="store_true",
        help="Do not provision the heavy local Studio Sound backend after editable install.",
    )
    args = parser.parse_args()

    if os.environ.get("EDDY_INSTALL_DRY_RUN"):
        print({"repo": str(ROOT), "targets": [str(p / "eddy") for p in _candidate_skill_dirs(args.agent)]})
        return
    results = install(args.agent, copy=args.copy)
    if args.install_editable:
        install_editable(install_studio_sound=not args.skip_studio_sound)
    for item in results:
        print(f"{item['action']}: {item['target']}")


if __name__ == "__main__":
    main()
