"""Notify-only update detection for installed Eddy checkouts."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(repo: Path, args: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def check_for_update(repo: Path | None = None, remote: str = "origin", branch: str = "main") -> dict:
    """Return update status without mutating the checkout.

    This intentionally uses `git ls-remote`, not `git fetch` or `git pull`, so a user-installed
    skill can learn that a newer Eddy exists without changing files under the agent.
    """
    root = Path(repo or default_repo_root()).expanduser().resolve()
    if not (root / ".git").exists():
        return {"ok": False, "status": "not_git_checkout", "repo": str(root), "mutated": False}

    local = _run(root, ["rev-parse", "HEAD"])
    if local.returncode != 0:
        return {"ok": False, "status": "local_rev_failed", "repo": str(root), "mutated": False, "error": local.stderr[-300:]}

    remote_url = _run(root, ["remote", "get-url", remote])
    if remote_url.returncode != 0:
        return {
            "ok": False,
            "status": "remote_missing",
            "repo": str(root),
            "remote": remote,
            "mutated": False,
            "error": remote_url.stderr[-300:],
        }

    remote_ref = _run(root, ["ls-remote", remote, f"refs/heads/{branch}"], timeout=45)
    if remote_ref.returncode != 0:
        return {
            "ok": False,
            "status": "remote_check_failed",
            "repo": str(root),
            "remote": remote,
            "branch": branch,
            "mutated": False,
            "error": remote_ref.stderr[-300:],
        }
    line = remote_ref.stdout.strip().splitlines()[0] if remote_ref.stdout.strip() else ""
    remote_sha = line.split()[0] if line else ""
    local_sha = local.stdout.strip()
    if not remote_sha:
        return {
            "ok": False,
            "status": "remote_branch_missing",
            "repo": str(root),
            "remote": remote,
            "branch": branch,
            "mutated": False,
        }
    status = "up_to_date" if local_sha == remote_sha else "update_available"
    return {
        "ok": True,
        "status": status,
        "repo": str(root),
        "remote": remote,
        "branch": branch,
        "local_sha": local_sha,
        "remote_sha": remote_sha,
        "remote_url": remote_url.stdout.strip(),
        "mutated": False,
        "next_action": "Review changes, then run git pull manually if you want them." if status == "update_available" else "None.",
    }
