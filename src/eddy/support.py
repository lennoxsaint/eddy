"""Redacted, media-free support bundles for blocked Eddy jobs."""

from __future__ import annotations

import io
import json
import re
import tarfile
from pathlib import Path
from typing import Any


SAFE_SUPPORT_FILES = {"state.json", "verification.json", "worker-error.json", "receipts.jsonl"}
SECRET_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(rb"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{8,}"),
    re.compile(rb"dx_(?:bearer|secret)_[A-Za-z0-9-]{8,}"),
    re.compile(rb"(?i)bearer\s+[A-Za-z0-9._~-]{8,}"),
    re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(rb"https?://[^\s\"']+[?&][^\s\"']+"),
    re.compile(rb"/(?:Users|home|private|tmp)/[^\s\"']+"),
)


def create_support_bundle(run_dir: Path, output: Path) -> Path:
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run_dir_missing:{run_dir}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(run_dir.rglob("*")):
            if not path.is_file() or path.name not in SAFE_SUPPORT_FILES:
                continue
            relative = path.relative_to(run_dir).as_posix()
            redacted = _redact(_safe_payload(path))
            info = tarfile.TarInfo(relative)
            info.size = len(redacted)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(redacted))
    return output


def _redact(payload: bytes) -> bytes:
    for pattern in SECRET_PATTERNS:
        payload = pattern.sub(b"[REDACTED]", payload)
    return payload


def _safe_code(value: object) -> str:
    text = str(value)
    return text if re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", text) else "[REDACTED]"


def _safe_payload(path: Path) -> bytes:
    if path.name == "receipts.jsonl":
        rows = []
        for line in path.read_text(errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(
                {
                    key: (_safe_code(value) if key in {"event", "state", "job_id", "at"} else value)
                    for key, value in row.items()
                    if key in {"event", "state", "job_id", "at"}
                }
            )
        return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
    try:
        payload = json.loads(path.read_text(errors="replace"))
    except json.JSONDecodeError:
        return b'{"status":"unreadable"}\n'
    safe: dict[str, Any]
    if path.name == "state.json":
        safe = {
            "id": _safe_code(payload.get("id", "UNKNOWN")),
            "state": _safe_code(payload.get("state", "UNKNOWN")),
            "blockers": [_safe_code(item) for item in payload.get("blockers", [])],
        }
    elif path.name == "verification.json":
        safe = {
            "gates": {
                _safe_code(key): bool(value) for key, value in payload.get("gates", {}).items()
            },
            "blockers": [_safe_code(item) for item in payload.get("blockers", [])],
        }
    else:
        safe = {
            "action": _safe_code(payload.get("action", "UNKNOWN")),
            "blocker": _safe_code(payload.get("blocker", "UNKNOWN")),
        }
    return (json.dumps(safe, sort_keys=True) + "\n").encode()
