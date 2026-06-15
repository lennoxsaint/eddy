"""Run lifecycle: create/open run dirs, source discovery, read-only hash guard."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from eddy.config import load_config
from eddy.loop.receipts import Receipts

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi", ".ts", ".mts", ".m2ts", ".3gp", ".wmv", ".flv"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif"}


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
        ext = source.suffix.lower()
        if ext not in VIDEO_EXTS and ext not in AUDIO_EXTS:
            raise SourceError(f"not a video/audio file: {source}")
        # audio-only sources are accepted so podcasters can `eddy transcribe`; `eddy run` still
        # needs a video stream and will fail loud at the decodability preflight (with a clear hint).
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
        elif p.suffix.lower() in AUDIO_EXTS and "mic" in stem:
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
    incoming_sha = {k: sha256_file(v) for k, v in sources.items()}
    run_dir = cfg.runs_dir / (slug or default_slug(source))
    manifest_path = run_dir / "manifest.json"

    if manifest_path.exists():
        m = json.loads(manifest_path.read_text())
        # wrong-footage guard: a run dir is bound to the exact footage it was opened with.
        # The old code reused any existing dir for the slug WITHOUT re-checking the source
        # hashes, so a slug collision silently edited the WRONG video and bypassed the
        # source-mutation guarantee. Refuse unless the incoming footage hash-matches.
        if incoming_sha != m.get("source_sha256"):
            raise SourceError(
                f"slug {run_dir.name!r} already exists with DIFFERENT source footage "
                f"(sha256 mismatch). Pass a different --slug, or delete {run_dir} to start over."
            )
        Receipts(run_dir).log("run_reopened", resume=resume, sources=m.get("sources"))
        return run_dir

    # --resume now means something: there must be a run to resume.
    if resume:
        raise SourceError(
            f"nothing to resume: no run at {run_dir}. Drop --resume to start a new run."
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("transcript", "iterations", "final"):
        (run_dir / sub).mkdir(exist_ok=True)
    manifest = {
        "slug": run_dir.name,
        "sources": {k: str(v) for k, v in sources.items()},
        "source_sha256": incoming_sha,
        "config": cfg.model_dump(),
        "eddy_version": __import__("eddy").__version__,
    }
    from eddy.atomicio import atomic_write_text

    atomic_write_text(manifest_path, json.dumps(manifest, indent=2))
    Receipts(run_dir).log("run_opened", sources=manifest["sources"], eddy_version=manifest["eddy_version"])
    return run_dir


def manifest(run_dir: Path) -> dict:
    return json.loads((Path(run_dir) / "manifest.json").read_text())


def assert_sources_decodable(sources: dict[str, str]) -> None:
    """Preflight: every video source must actually decode (a real video stream + duration). Fails
    loud with an actionable message instead of a cryptic mid-pipeline ffmpeg crash on a corrupt,
    truncated, 0-byte, or unsupported file. Run right after open_run, before transcription."""
    from eddy.media.probe import stream_summary

    for name, path in sources.items():
        if name == "mic":
            continue  # audio-only companion track; no video stream expected
        p = Path(path)
        try:
            s = stream_summary(p)
        except Exception as e:
            raise SourceError(f"cannot decode {name} source {p}: {str(e)[:200]} — corrupt or unsupported?") from e
        if s["video"] is None:
            if p.suffix.lower() in AUDIO_EXTS:
                raise SourceError(
                    f"{name} source {p} is audio-only — `eddy run` edits video. "
                    f"Run `eddy transcribe {p}` for the transcript, or provide a video source."
                )
            raise SourceError(f"{name} source {p} has no decodable video stream (audio-only or corrupt?)")
        if s["duration_s"] <= 0:
            raise SourceError(f"{name} source {p} has unknown/zero duration — corrupt or truncated?")


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
