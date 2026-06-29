#!/usr/bin/env python3
"""Guarded Eddy trunk shipper: gates -> commit -> push main -> optional stable tag."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bin_path(name: str) -> str:
    local = ROOT / ".venv" / "bin" / name
    if local.exists():
        return str(local)
    found = shutil.which(name)
    return found or name


def run(cmd: list[str], *, env: dict[str, str] | None = None, dry_run: bool = False) -> None:
    printable = " ".join(cmd)
    print(f"+ {printable}")
    if dry_run:
        return
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def capture(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, text=True).strip()


def project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def tag_matches_version(tag: str, version: str) -> bool:
    return tag == f"v{version}"


def is_run_artifact(path: str) -> bool:
    clean = path.strip()
    if clean.startswith(("runs/", ".eddy/", "work/")):
        return True
    return "/runs/" in clean or clean.endswith("/receipts.jsonl")


def status_paths() -> list[str]:
    out = capture(["git", "status", "--short", "--untracked-files=all"])
    paths: list[str] = []
    for line in out.splitlines():
        if not line:
            continue
        # porcelain v1: XY path, with rename as "old -> new"; check both sides conservatively.
        path = line[3:]
        paths.extend(part.strip() for part in path.split(" -> "))
    return paths


def ensure_branch_main() -> None:
    branch = capture(["git", "branch", "--show-current"])
    if branch != "main":
        raise SystemExit(f"Refusing to ship from {branch!r}; Eddy trunk ships from main only.")


def ensure_no_run_artifacts() -> None:
    bad = [path for path in status_paths() if is_run_artifact(path)]
    tracked_runs = capture(["git", "ls-files", "runs", "work", ".eddy"])
    if tracked_runs:
        bad.extend(tracked_runs.splitlines())
    if bad:
        raise SystemExit("Refusing to ship dirty run/scratch artifacts:\n" + "\n".join(f"- {p}" for p in bad))


def ensure_tag_ok(tag: str | None) -> None:
    if not tag:
        return
    version = project_version()
    if not tag_matches_version(tag, version):
        raise SystemExit(f"Tag {tag!r} does not match pyproject version {version!r}; expected v{version}.")
    local = capture(["git", "tag", "--list", tag])
    if local:
        raise SystemExit(f"Tag {tag!r} already exists locally.")
    remote = capture(["git", "ls-remote", "--tags", "origin", tag])
    if remote:
        raise SystemExit(f"Tag {tag!r} already exists on origin.")


def gate_commands(tag: str | None) -> list[tuple[list[str], dict[str, str] | None]]:
    pytest = bin_path("pytest")
    commands: list[tuple[list[str], dict[str, str] | None]] = [
        ([bin_path("ruff"), "check", "src", "tests"], None),
        ([bin_path("mypy"), "src/eddy"], None),
        ([pytest, "-q", "--cov=eddy", "--cov-report=term-missing"], None),
        ([sys.executable, "scripts/public_scrub_check.py"], None),
        (["git", "diff", "--check"], None),
        (["git", "diff", "--cached", "--check"], None),
    ]
    if tag:
        env = dict(os.environ)
        env["EDDY_GOLDEN"] = "1"
        commands.append(([pytest, "tests/test_golden.py", "-q"], env))
    return commands


def stage_changes(*, dry_run: bool = False) -> None:
    run(["git", "add", "-A"], dry_run=dry_run)
    if not dry_run:
        staged = capture(["git", "diff", "--cached", "--name-only"])
        if not staged:
            raise SystemExit("Nothing staged; refusing to create an empty Eddy ship commit.")
        bad = [path for path in staged.splitlines() if is_run_artifact(path)]
        if bad:
            raise SystemExit("Refusing to stage run/scratch artifacts:\n" + "\n".join(f"- {p}" for p in bad))


def commit_push(message: str, tag: str | None, *, dry_run: bool = False) -> None:
    run(["git", "commit", "-m", message], dry_run=dry_run)
    run(["git", "push", "origin", "main"], dry_run=dry_run)
    if tag:
        run(["git", "tag", tag], dry_run=dry_run)
        run(["git", "push", "origin", tag], dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", required=True, help="Commit message for the trunk ship.")
    parser.add_argument("--tag", help="Optional stable tag to create and push, e.g. v1.10.5.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands and validations without running them.")
    args = parser.parse_args(argv)

    ensure_branch_main()
    ensure_no_run_artifacts()
    ensure_tag_ok(args.tag)
    stage_changes(dry_run=args.dry_run)
    for cmd, env in gate_commands(args.tag):
        run(cmd, env=env, dry_run=args.dry_run)
    commit_push(args.message, args.tag, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
