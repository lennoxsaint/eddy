"""Redacted, media-free support bundles for blocked Eddy jobs."""

from __future__ import annotations

import io
import re
import tarfile
from pathlib import Path


TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".log"}
SECRET_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(rb"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{8,}"),
    re.compile(rb"dx_(?:bearer|secret)_[A-Za-z0-9-]{8,}"),
)


def create_support_bundle(run_dir: Path, output: Path) -> Path:
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run_dir_missing:{run_dir}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(run_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            relative = path.relative_to(run_dir).as_posix()
            redacted = _redact(path.read_bytes())
            info = tarfile.TarInfo(relative)
            info.size = len(redacted)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(redacted))
    return output


def _redact(payload: bytes) -> bytes:
    for pattern in SECRET_PATTERNS:
        payload = pattern.sub(b"[REDACTED]", payload)
    return payload

