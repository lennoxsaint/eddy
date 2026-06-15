"""Opt-in, anonymized failure beacon for fleet bug-triage.

OFF by default. When the user opts in (telemetry.enabled + telemetry.endpoint), a crash sends ONLY
anonymized environment + error-class data — never footage, transcript, paths, or the error message
(which can contain a path). Best-effort: telemetry never breaks a run.
"""

from __future__ import annotations

import platform
import shutil
import subprocess


def _ffmpeg_version_line() -> str:
    if not shutil.which("ffmpeg"):
        return "absent"
    try:
        out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        return out.stdout.splitlines()[0][:60] if out.stdout else "?"
    except Exception:
        return "?"


def beacon_payload(error: BaseException, stage: str) -> dict:
    """Anonymized only: version/OS/python/ffmpeg/stage/error CLASS. No message, no paths, no content."""
    import eddy

    return {
        "eddy_version": eddy.__version__,
        "platform": platform.system(),
        "python": platform.python_version(),
        "ffmpeg": _ffmpeg_version_line(),
        "stage": stage,
        "error_class": type(error).__name__,
    }


def send_failure_beacon(error: BaseException, stage: str, cfg=None) -> dict | None:
    """No-op unless opted in. Returns the sent payload (for tests/audit), or None when disabled."""
    if cfg is None:
        from eddy.config import load_config

        cfg = load_config()
    if not cfg.telemetry.enabled or not cfg.telemetry.endpoint:
        return None
    payload = beacon_payload(error, stage)
    try:
        import httpx

        httpx.post(cfg.telemetry.endpoint, json=payload, timeout=5)
    except Exception:
        pass  # best-effort; telemetry must never break the run
    return payload
