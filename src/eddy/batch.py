"""Batch/queue runner for agencies: process many sources, continuing past per-item failures, with
a structured summary; plus a fleet list of existing runs."""

from __future__ import annotations

import json
from pathlib import Path

from eddy import log
from eddy.runs import VIDEO_EXTS


def discover_batch_sources(path: Path) -> list[Path]:
    """A batch root: each immediate subdirectory (a footage dir) and each top-level video file is one
    source. A single file/dir is itself one source."""
    path = Path(path).expanduser()
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    # heuristic: if it directly contains video files and no subdirs of footage, treat it as ONE source
    subdirs = [p for p in sorted(path.iterdir()) if p.is_dir()]
    videos = [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    if videos and not subdirs:
        return [path]
    return subdirs + videos


def run_batch(sources: list[Path], runner=None, **opts) -> dict:
    """Run each source through `runner` (default autonomous_run), continuing past per-item failures.
    Returns a structured summary suitable for headless/CI consumption."""
    if runner is None:
        from eddy.loop.controller import autonomous_run as runner
    items: list[dict] = []
    for src in sources:
        try:
            runner(source=src, **opts)
            items.append({"source": str(src), "status": "ok"})
        except Exception as e:
            from eddy.errors import friendly_error

            head, _ = friendly_error(e)
            items.append({"source": str(src), "status": "failed", "error": head[:200]})
    return {
        "total": len(sources),
        "succeeded": sum(1 for i in items if i["status"] == "ok"),
        "failed": sum(1 for i in items if i["status"] == "failed"),
        "items": items,
    }


def list_runs(runs_dir: Path) -> list[dict]:
    """Fleet list: every run under runs_dir with its phase + best iteration."""
    runs_dir = Path(runs_dir)
    if not runs_dir.exists():
        return []
    out = []
    for d in sorted(runs_dir.iterdir()):
        if not d.is_dir() or not (d / "manifest.json").exists():
            continue
        state: dict = {}
        sp = d / "state.json"
        if sp.exists():
            try:
                state = json.loads(sp.read_text())
            except Exception as exc:
                log.debug("batch: unreadable state.json for %s: %s", d.name, exc)
                state = {}
        out.append({"slug": d.name, "phase": state.get("phase", "?"), "best_iter": state.get("best_iter")})
    return out
