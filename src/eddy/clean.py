"""Reclaim disk from a run by pruning scratch intermediates (segment dirs, proxy renders, the 16k
WAV, caption layout scratch), keeping the deliverables (final/, manifest, state, receipts, and each
iteration's decisions/EDL/sim audit trail). A run can otherwise leave many GB of segment scratch."""

from __future__ import annotations

import shutil
from pathlib import Path

# directories (removed whole) and files that are re-derivable scratch
_SCRATCH_DIR_GLOBS = ["**/*_segments", "**/layout-segments", "**/caption-frames"]
_SCRATCH_FILE_GLOBS = [
    "transcript/audio-16k.wav",
    "iterations/**/proxy*.mp4",
    "iterations/**/*-proxy.mp4",
    "iterations/trim-proxy.mp4",
]


# PII-laden artifacts a GDPR/CCPA "delete my data" request targets: the transcript (the person's
# words), extracted face frames, and derived caption/subtitle text. Deliverables (final video,
# titles) stay unless --full. Source footage is never written by Eddy (read-only), so not here.
_PII_DIR_GLOBS = ["transcript", "**/thumbnails/refs"]
_PII_FILE_GLOBS = [
    "final/transcript.md", "final/subtitles.srt", "final/subtitles.vtt",
    "**/beats.json", "**/words.json",
]


def dir_size_bytes(path: str | Path) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def clean_run(run_dir: str | Path, dry_run: bool = False) -> dict:
    """Prune scratch; return what was (or would be) freed. Deliverables are never touched."""
    run_dir = Path(run_dir)
    freed = 0
    removed: list[str] = []
    for g in _SCRATCH_DIR_GLOBS:
        for d in sorted(run_dir.glob(g)):
            if d.is_dir():
                freed += dir_size_bytes(d)
                removed.append(str(d.relative_to(run_dir)))
                if not dry_run:
                    shutil.rmtree(d, ignore_errors=True)
    for g in _SCRATCH_FILE_GLOBS:
        for f in sorted(run_dir.glob(g)):
            if f.is_file():
                freed += f.stat().st_size
                removed.append(str(f.relative_to(run_dir)))
                if not dry_run:
                    f.unlink(missing_ok=True)
    return {"freed_mb": round(freed / 2**20, 1), "removed": removed, "dry_run": dry_run}


def purge_run(run_dir: str | Path, full: bool = False, dry_run: bool = False) -> dict:
    """GDPR/CCPA purge: remove the PII artifacts (transcript, face frames, derived caption text).
    full=True removes the entire run directory (complete erasure)."""
    run_dir = Path(run_dir)
    if full:
        # delete-safety: refuse to rmtree a path that isn't recognizably an Eddy run
        if not ((run_dir / "manifest.json").exists() or (run_dir / "state.json").exists()):
            from eddy.runs import SourceError

            raise SourceError(f"{run_dir} doesn't look like an Eddy run (no manifest.json/state.json) — refusing --full")
        size = dir_size_bytes(run_dir)
        if not dry_run:
            shutil.rmtree(run_dir, ignore_errors=True)
        return {"freed_mb": round(size / 2**20, 1), "removed": [f"{run_dir.name}/ (entire run)"], "full": True, "dry_run": dry_run}

    freed = 0
    removed: list[str] = []
    for g in _PII_DIR_GLOBS:
        for d in sorted(run_dir.glob(g)):
            if d.is_dir():
                freed += dir_size_bytes(d)
                removed.append(str(d.relative_to(run_dir)))
                if not dry_run:
                    shutil.rmtree(d, ignore_errors=True)
    for g in _PII_FILE_GLOBS:
        for f in sorted(run_dir.glob(g)):
            if f.is_file():
                freed += f.stat().st_size
                removed.append(str(f.relative_to(run_dir)))
                if not dry_run:
                    f.unlink(missing_ok=True)
    return {"freed_mb": round(freed / 2**20, 1), "removed": removed, "full": False, "dry_run": dry_run}
