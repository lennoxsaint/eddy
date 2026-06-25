#!/usr/bin/env python3
"""Stable-tag bootstrapper for the Codex Eddy plugin.

This module is intentionally standard-library only. It runs before Eddy itself is installed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

REPO_URL = "https://github.com/lennoxsaint/eddy.git"
STATE_VERSION = 1
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    def as_receipt(self) -> dict:
        return {
            "args": self.args,
            "returncode": self.returncode,
            "stdout_tail": self.stdout[-500:],
            "stderr_tail": self.stderr[-500:],
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_stable_tag(tag: str) -> tuple[int, int, int] | None:
    match = TAG_RE.match(tag.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def select_latest_stable_tag(ls_remote_output: str) -> str:
    tags: list[tuple[tuple[int, int, int], str]] = []
    for line in ls_remote_output.splitlines():
        ref = line.split()[-1] if line.split() else ""
        tag = ref.removeprefix("refs/tags/")
        parsed = parse_stable_tag(tag)
        if parsed is not None:
            tags.append((parsed, tag))
    if not tags:
        raise RuntimeError("no_stable_tags_found")
    return sorted(tags)[-1][1]


def run(args: list[str], timeout: int = 900, cwd: Path | None = None) -> CommandResult:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return CommandResult(args=args, returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def check(args: list[str], timeout: int = 900, cwd: Path | None = None) -> CommandResult:
    result = run(args, timeout=timeout, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(json.dumps({"blocker": "command_failed", "command": result.as_receipt()}))
    return result


def latest_stable_tag(repo_url: str = REPO_URL) -> str:
    result = check(["git", "ls-remote", "--tags", "--refs", repo_url, "refs/tags/v*"], timeout=60)
    return select_latest_stable_tag(result.stdout)


def home_root(home: Path | None = None) -> Path:
    return Path(home or (Path.home() / ".eddy")).expanduser().resolve()


def state_file(home: Path | None = None) -> Path:
    return home_root(home) / "plugin-state.json"


def venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def venv_tool(venv: Path, name: str) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / f"{name}.exe"
    return venv / "bin" / name


def active_state(home: Path | None = None) -> dict:
    path = state_file(home)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"status": "state_unreadable", "path": str(path)}


def write_state(payload: dict, home: Path | None = None) -> None:
    root = home_root(home)
    root.mkdir(parents=True, exist_ok=True)
    path = state_file(root)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


@contextmanager
def update_lock(home: Path | None = None) -> Iterator[None]:
    root = home_root(home)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "plugin-update.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"update_lock_exists:{lock}") from exc
    try:
        os.write(fd, utc_now().encode("utf-8"))
        os.close(fd)
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def install_candidate(
    *,
    repo_url: str,
    tag: str,
    root: Path,
    python: str,
    skip_studio_sound: bool,
) -> dict:
    receipts: list[dict] = []
    tmp_root = Path(tempfile.mkdtemp(prefix="plugin-update-", dir=str(root)))
    candidate_source = tmp_root / "source"
    candidate_venv = tmp_root / "venv"
    try:
        receipts.append(
            check(
                ["git", "clone", "--depth", "1", "--branch", tag, repo_url, str(candidate_source)],
                timeout=240,
            ).as_receipt()
        )
        receipts.append(check([python, "-m", "venv", str(candidate_venv)], timeout=240).as_receipt())
        py = venv_python(candidate_venv)
        receipts.append(check([str(py), "-m", "pip", "install", "--upgrade", "pip"], timeout=300).as_receipt())
        receipts.append(check([str(py), "-m", "pip", "install", "-e", f"{candidate_source}[mcp]"], timeout=900).as_receipt())
        if not skip_studio_sound:
            receipts.append(check([str(venv_tool(candidate_venv, "eddy")), "studio-sound", "install"], timeout=1800).as_receipt())
        receipts.append(
            check(
                [
                    str(py),
                    "-c",
                    "import eddy, eddy.cli, eddy.mcp_server.server; print(eddy.__version__)",
                ],
                timeout=60,
            ).as_receipt()
        )
        return {
            "tmp_root": str(tmp_root),
            "source": str(candidate_source),
            "venv": str(candidate_venv),
            "receipts": receipts,
        }
    except Exception:
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise


def swap_active(root: Path, candidate: dict, tag: str, repo_url: str, receipts: list[dict]) -> dict:
    active_source = root / "source"
    active_venv = root / "venv"
    previous_source = root / "source.previous"
    previous_venv = root / "venv.previous"
    tmp_root = Path(candidate["tmp_root"])
    source = Path(candidate["source"])
    venv = Path(candidate["venv"])

    for previous in (previous_source, previous_venv):
        if previous.exists():
            shutil.rmtree(previous, ignore_errors=True)

    moved_current = False
    try:
        if active_source.exists():
            active_source.rename(previous_source)
            moved_current = True
        if active_venv.exists():
            active_venv.rename(previous_venv)
        source.rename(active_source)
        venv.rename(active_venv)
        shutil.rmtree(tmp_root, ignore_errors=True)
        payload = {
            "state_version": STATE_VERSION,
            "status": "active",
            "active_tag": tag,
            "repo_url": repo_url,
            "updated_at": utc_now(),
            "source": str(active_source),
            "venv": str(active_venv),
            "receipts": receipts,
        }
        write_state(payload, root)
        return payload
    except Exception:
        shutil.rmtree(active_source, ignore_errors=True)
        shutil.rmtree(active_venv, ignore_errors=True)
        if moved_current and previous_source.exists():
            previous_source.rename(active_source)
        if previous_venv.exists():
            previous_venv.rename(active_venv)
        raise


def ensure_latest_stable(
    *,
    repo_url: str = REPO_URL,
    home: Path | None = None,
    dry_run: bool = False,
    python: str | None = None,
    skip_studio_sound: bool | None = None,
    tag: str | None = None,
) -> dict:
    root = home_root(home)
    root.mkdir(parents=True, exist_ok=True)
    selected_tag = tag or latest_stable_tag(repo_url)
    state = active_state(root)
    active_tag = state.get("active_tag")
    active_py = venv_python(root / "venv")
    active_source = root / "source"
    skip_audio = (
        os.environ.get("EDDY_PLUGIN_SKIP_STUDIO_SOUND") == "1"
        if skip_studio_sound is None
        else skip_studio_sound
    )
    payload = {
        "state_version": STATE_VERSION,
        "repo_url": repo_url,
        "latest_tag": selected_tag,
        "active_tag": active_tag,
        "source": str(active_source),
        "venv": str(root / "venv"),
        "checked_at": utc_now(),
        "mutated": False,
    }
    if active_tag == selected_tag and active_source.exists() and active_py.exists():
        payload.update({"status": "up_to_date", "ok": True})
        write_state({**state, **payload, "status": "active"}, root)
        return payload
    if dry_run:
        payload.update(
            {
                "status": "would_update",
                "ok": True,
                "mutated": False,
                "skip_studio_sound": skip_audio,
                "planned_steps": [
                    "git clone latest stable tag",
                    "create managed virtualenv",
                    "pip install Eddy with MCP extra",
                    "install Studio Sound backend unless skipped",
                    "smoke check and atomic swap",
                ],
            }
        )
        return payload
    with update_lock(root):
        try:
            candidate = install_candidate(
                repo_url=repo_url,
                tag=selected_tag,
                root=root,
                python=python or sys.executable,
                skip_studio_sound=skip_audio,
            )
            receipts = list(candidate.get("receipts", []))
            result = swap_active(root, candidate, selected_tag, repo_url, receipts)
            return {
                **payload,
                "status": "updated",
                "ok": True,
                "mutated": True,
                "skip_studio_sound": skip_audio,
                "receipts": receipts,
                "active_state": result,
            }
        except Exception as exc:
            failure = {
                **payload,
                "status": "update_failed",
                "ok": False,
                "mutated": False,
                "blocker": str(exc),
                "previous_active_available": bool(active_source.exists() and active_py.exists()),
            }
            write_state(failure, root)
            if failure["previous_active_available"]:
                return failure
            raise


def main() -> int:
    result = ensure_latest_stable(dry_run="--dry-run" in sys.argv)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
