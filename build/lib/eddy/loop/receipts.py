"""Append-only receipts: every model call, ffmpeg command, gate verdict, ranking."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class Receipts:
    def __init__(self, run_dir: Path):
        self.path = run_dir / "receipts.jsonl"

    def log(self, event: str, **fields) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **fields}
        with self.path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
