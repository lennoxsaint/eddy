"""Run lifecycle: create/open run dirs, source discovery, read-only hash guard."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from eddy.config import load_config
from eddy.loop.receipts import Receipts

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v"}


class SourceError(RuntimeError):
    pass


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while data := f.read(chunk):
            h.update(data)
    return h.hexdigest()


def discover_sources(source: Path) -> dict[str, Path]:
    """camera/screen/mic discovery. A single file or a dir; degraded single
    composite is the baseline case."""
    source = source.expanduser().resolve()
    if source.is_file():
        if source.suffix.lower() not in VIDEO_EXTS:
            raise SourceError(f"not a video file: {source}")
        return {"camera": source}
    if not source.is_dir():
        raise SourceError(f"source not found: {source}")

    found: dict[str, Path] = {}
    files = [p for p in sorted(source.iterdir()) if p.is_file()]
    for p in files:
        stem = p.stem.lower()
        if p.suffix.lower() in VIDEO_EXTS:
            if "screen" in stem or "display" in stem:
                found.setdefault("screen", p)
            elif any(k in stem for k in ("camera", "cam", "webcam", "face", "talking")):
                found.setdefault("camera", p)
        elif p.suffix.lower() in {".wav", ".m4a"} and "mic" in stem:
            found.setdefault("mic", p)
    if "camera" not in found:
        videos = [p for p in files if p.suffix.lower() in VIDEO_EXTS]
        if len(videos) == 1:
            found["camera"] = videos[0]
        elif not videos:
            raise SourceError(f"no video files in {source}")
        else:
            raise SourceError(
                f"multiple videos in {source} and none named camera/screen — name them or pass a file"
            )
    return found


def default_slug(source: Path) -> str:
    base = source.stem if source.is_file() else source.name
    for noise in ("raw-video", "raw", "source"):
        if base == noise and source.parent.name:
            base = source.parent.parent.name if source.parent.name in ("raw", "source") else source.parent.name
            break
    return f"{date.today().isoformat()}-{base}"[:80]


def open_run(source: Path, slug: str | None = None, resume: bool = False) -> Path:
    cfg = load_config()
    sources = discover_sources(source)
    run_dir = cfg.runs_dir / (slug or default_slug(source))
    manifest_path = run_dir / "manifest.json"

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        return run_dir

    run_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("transcript", "iterations", "final"):
        (run_dir / sub).mkdir(exist_ok=True)
    manifest = {
        "slug": run_dir.name,
        "sources": {k: str(v) for k, v in sources.items()},
        "source_sha256": {k: sha256_file(v) for k, v in sources.items()},
        "config": load_config().model_dump(),
        "eddy_version": __import__("eddy").__version__,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    Receipts(run_dir).log("run_opened", sources=manifest["sources"])
    return run_dir


def manifest(run_dir: Path) -> dict:
    return json.loads((Path(run_dir) / "manifest.json").read_text())


def verify_sources_unmutated(run_dir: Path) -> dict:
    """Hard gate: re-hash sources; raise if anything changed."""
    m = manifest(run_dir)
    results = {}
    for name, path in m["sources"].items():
        current = sha256_file(Path(path))
        ok = current == m["source_sha256"][name]
        results[name] = ok
        if not ok:
            raise SourceError(f"SOURCE MUTATED: {path} hash changed during run")
    Receipts(Path(run_dir)).log("sources_verified", results=results)
    return results
