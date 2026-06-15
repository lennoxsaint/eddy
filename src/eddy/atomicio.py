"""Atomic file writes: write a sibling `.tmp` then `os.replace` (POSIX-atomic on the same fs).

A plain `Path.write_text()` truncates-then-writes; a crash, SIGKILL, OOM, or power loss
mid-write leaves a 0-byte or half-written file. For `state.json` and the per-iteration
`edl.json` that `--resume` reads back, that means an unrecoverable run. `os.replace` makes the
swap all-or-nothing: a reader sees either the old file or the new one, never a torn one.
"""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding=encoding) as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)  # atomic on the same filesystem
