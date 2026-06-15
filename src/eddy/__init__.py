"""Eddy — local-first agentic video editor."""

from __future__ import annotations


def _detect_version() -> str:
    """Honest version. This is a local, tag-per-milestone repo, so the git tag is the source of
    truth when running from a checkout (`0.1.0` was hardcoded and stale, so every receipt/manifest
    lied about which code produced it). Falls back to installed package metadata for a built/pipx
    install where there's no .git, then to a dev sentinel.
    """
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]  # src/eddy/__init__.py -> repo root
    if (repo / ".git").exists():
        try:
            out = subprocess.run(
                ["git", "-C", str(repo), "describe", "--tags", "--dirty", "--always"],
                capture_output=True, text=True, timeout=3,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip().lstrip("v")
        except Exception:
            pass
    try:
        from importlib.metadata import version

        return version("eddy")
    except Exception:
        return "0+unknown"


__version__ = _detect_version()
