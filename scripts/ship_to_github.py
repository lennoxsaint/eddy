#!/usr/bin/env python3
"""Guarded trunk ship for Eddy's canonical V3 repository."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REMOTE = "https://github.com/lennoxsaint/eddy.git"
GENERATED_PREFIXES = (
    "plugins/eddy/skills/eddy/",
    "integrations/claude-code/skills/eddy/",
)
PRIVATE_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".wav", ".m4a", ".mp3"}
PRIVATE_NAMES = {"source-lock.json", "receipts.jsonl", "provider-receipts.jsonl"}


def validate_repository(root: Path) -> None:
    branch = _git(root, "branch", "--show-current")
    remote = _git(root, "remote", "get-url", "origin")
    if branch != "main":
        raise RuntimeError(f"ship_requires_main_branch:{branch}")
    if remote.rstrip("/") != EXPECTED_REMOTE.rstrip("/"):
        raise RuntimeError(f"ship_remote_mismatch:{remote}")


def validate_allowlist(changed: set[str], allowed: set[str]) -> None:
    unexpected = sorted(
        path
        for path in changed
        if path not in allowed and not any(path.startswith(prefix) for prefix in GENERATED_PREFIXES)
    )
    if unexpected:
        raise RuntimeError(f"ship_unintended_changes:{','.join(unexpected)}")
    private = sorted(
        path
        for path in changed
        if Path(path).suffix.lower() in PRIVATE_SUFFIXES or Path(path).name in PRIVATE_NAMES
    )
    if private:
        raise RuntimeError(f"ship_private_run_artifacts:{','.join(private)}")


def changed_files(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    entries = result.stdout.decode().split("\0")
    paths: set[str] = set()
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status = entry[:2]
        path = entry[3:]
        if status[0] in {"R", "C"}:
            if index < len(entries) and entries[index]:
                path = entries[index]
                index += 1
        paths.add(path)
    return paths


def ship(*, includes: set[str], message: str, dry_run: bool) -> dict[str, object]:
    validate_repository(ROOT)
    _run([str(ROOT / ".venv" / "bin" / "python"), "scripts/sync_skill_surfaces.py"])
    changed = changed_files(ROOT)
    validate_allowlist(changed, includes)
    if not changed:
        raise RuntimeError("ship_no_changes")
    commands = [
        [str(ROOT / ".venv" / "bin" / "ruff"), "check", "src", "tests", "scripts"],
        [str(ROOT / ".venv" / "bin" / "mypy"), "src/eddy"],
        [
            str(ROOT / ".venv" / "bin" / "pytest"),
            "-q",
            "--cov=eddy",
            "--cov-report=term-missing",
        ],
        [str(ROOT / ".venv" / "bin" / "python"), "scripts/sync_skill_surfaces.py", "--check"],
        [str(ROOT / ".venv" / "bin" / "python"), "scripts/public_scrub_check.py"],
        ["git", "diff", "--cached", "--check"],
    ]
    if dry_run:
        return {
            "status": "dry_run",
            "changed": sorted(changed),
            "commands": commands,
            "would_commit": message,
            "would_push": "origin main",
            "would_refresh_plugin": True,
        }
    _run(["git", "add", "--", *sorted(changed)])
    staged = set(_git(ROOT, "diff", "--cached", "--name-only").splitlines())
    if staged != changed:
        raise RuntimeError("ship_staged_allowlist_mismatch")
    try:
        for command in commands:
            _run(command)
    except Exception:
        subprocess.run(
            ["git", "restore", "--staged", "--", *sorted(changed)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        raise
    _run(["git", "commit", "-m", message])

    _run([str(ROOT / ".venv" / "bin" / "python"), "scripts/sync_skill_surfaces.py"])
    projection_changes = changed_files(ROOT)
    if projection_changes:
        if not all(any(path.startswith(prefix) for prefix in GENERATED_PREFIXES) for path in projection_changes):
            raise RuntimeError("ship_post_commit_projection_drift_unexpected")
        _run(["git", "add", "--", *sorted(projection_changes)])
        _run(["git", "commit", "-m", "Regenerate Eddy platform projections"])
    _run([str(ROOT / ".venv" / "bin" / "python"), "scripts/sync_skill_surfaces.py", "--check"])
    _run(["git", "push", "origin", "main"])
    commit = _git(ROOT, "rev-parse", "HEAD")
    ci = _wait_for_ci(commit)
    plugin = _run_json(
        [str(ROOT / ".venv" / "bin" / "python"), "scripts/install_owner_plugin.py"]
    )
    doctor = _run_json([str(ROOT / ".venv" / "bin" / "eddy"), "sync-doctor"])
    if not doctor.get("owner_plugin", {}).get("ok"):
        raise RuntimeError("ship_owner_plugin_verification_failed")
    return {
        "status": "shipped",
        "commit": commit,
        "ci": ci,
        "plugin": plugin,
        "sync_doctor": doctor,
    }


def _wait_for_ci(commit: str, *, timeout_s: int = 900) -> dict[str, object]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                "lennoxsaint/eddy",
                "--commit",
                commit,
                "--limit",
                "1",
                "--json",
                "databaseId,status,conclusion,url",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            rows = json.loads(result.stdout or "[]")
            if rows:
                row = rows[0]
                if row.get("status") == "completed":
                    if row.get("conclusion") != "success":
                        raise RuntimeError(f"ship_ci_failed:{row.get('url')}")
                    return row
        time.sleep(5)
    raise RuntimeError(f"ship_ci_timeout:{commit}")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _run(command: list[str]) -> str:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "blocker": "ship_command_failed",
                    "command": command,
                    "stdout_tail": result.stdout[-800:],
                    "stderr_tail": result.stderr[-1200:],
                }
            )
        )
    return result.stdout


def _run_json(command: list[str]) -> dict[str, object]:
    return json.loads(_run(command))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include", action="append", default=[], help="intended repo-relative path")
    parser.add_argument("--commit-message", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        payload = ship(
            includes={str(Path(path)) for path in args.include},
            message=args.commit_message,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - guarded ship prints the exact blocker
        print(json.dumps({"status": "blocked", "blocker": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
