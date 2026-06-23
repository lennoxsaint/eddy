"""Hard gates on rendered artifacts. These can never be overruled by the judge."""

from __future__ import annotations

import json
import re
import importlib
from pathlib import Path
from typing import Any

from eddy.config import EddyConfig
from eddy.edit.schema import Edl
from eddy.media.probe import stream_summary

PILImage: Any
try:
    PILImage = importlib.import_module("PIL.Image")
except Exception:  # pragma: no cover
    PILImage = None


def probe_clean(video: Path) -> dict:
    try:
        s = stream_summary(video)
        ok = s["video"] is not None and s["audio"] is not None and s["duration_s"] > 1
        return {"gate": "probe_clean", "pass": ok, "summary": s}
    except Exception as e:
        return {"gate": "probe_clean", "pass": False, "error": str(e)[:300]}


def av_drift(video: Path, edl: Edl, max_drift_s: float) -> dict:
    actual = stream_summary(video)["duration_s"]
    drift = abs(actual - edl.total_duration_s)
    return {
        "gate": "av_drift",
        "pass": drift <= max_drift_s,
        "actual_s": round(actual, 2),
        "edl_s": edl.total_duration_s,
        "drift_s": round(drift, 2),
    }


def _detect(video: Path, run_dir: Path, filt: str, tag: str, audio: bool = False) -> list[str]:
    """Run a detect filter and return matching stderr lines.

    Routes audio filters (silencedetect) to -af and video filters (black/freeze) to -vf — the old
    heuristic sent silencedetect to -vf, where it errored, and the non-zero exit was ignored, so the
    dead-air/silent-motion gates silently PASSED on a failed probe. A failed detect now raises so the
    gate fails loud (caught per-gate) instead of false-passing."""
    import subprocess

    from eddy.media.ffmpeg import FFMPEG, FfmpegError

    flag = "-af" if audio else "-vf"
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(video), flag, filt, "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800,
    )
    if proc.returncode != 0:
        raise FfmpegError(f"detect '{tag}' failed ({proc.returncode}): {proc.stderr[-500:]}")
    return [ln for ln in proc.stderr.splitlines() if tag in ln]


def black_or_frozen(video: Path, run_dir: Path) -> dict:
    from eddy.media.ffmpeg import FfmpegError

    try:
        black = _detect(video, run_dir, "blackdetect=d=0.5:pix_th=0.10", "blackdetect")
        # screen-share content sits visually static for long stretches while the
        # creator talks — only a 60s+ freeze indicates a genuinely stuck render
        freeze = _detect(video, run_dir, "freezedetect=n=-60dB:d=60", "freeze_start")
    except FfmpegError as e:
        return {"gate": "black_or_frozen", "pass": False, "error": str(e)[:300]}
    return {
        "gate": "black_or_frozen",
        "pass": not black and not freeze,
        "black": black[:5],
        "frozen": freeze[:5],
    }


def _blink_flag_from_luma(before: float, middle: float, after: float) -> bool:
    """Detect a splice flash: the middle frame goes near-black/near-white while neighbours do not."""
    near_blank = middle <= 8 or middle >= 247
    neighbours_not_blank = 12 < before < 243 and 12 < after < 243
    sharp_return = abs(before - middle) >= 45 and abs(after - middle) >= 45
    return bool(near_blank and neighbours_not_blank and sharp_return)


def _frame_luma(path: Path) -> float:
    if PILImage is None:
        raise RuntimeError("Pillow unavailable")
    img = PILImage.open(path).convert("L").resize((32, 18))
    hist = img.histogram()
    total = sum(hist) or 1
    return sum(i * c for i, c in enumerate(hist)) / total


def visual_blink_gate(video: Path, edl: Edl, run_dir: Path, sample_window_s: float = 0.04) -> dict:
    """Sample frames around every output splice and fail if a black/white flash appears at the cut."""
    if len(edl.ranges) <= 1:
        return {"gate": "visual_blink", "pass": True, "splices_checked": 0, "flashes": []}
    from eddy.media.frames import extract_frame

    splices = []
    cursor = 0.0
    for r in edl.ranges[:-1]:
        cursor += (r.end - r.start) / (r.speed or 1.0)
        splices.append(cursor)
    out_dir = Path(run_dir) / "qa" / "blink-frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    flashes = []
    for i, t in enumerate(splices):
        frames = []
        try:
            for tag, at in (("before", t - sample_window_s), ("middle", t), ("after", t + sample_window_s)):
                p = out_dir / f"splice-{i:04d}-{tag}.jpg"
                extract_frame(video, at, p, run_dir, height=180)
                frames.append(_frame_luma(p))
        except Exception as e:
            return {"gate": "visual_blink", "pass": False, "error": str(e)[:300], "splice": i}
        if _blink_flag_from_luma(*frames):
            flashes.append({"splice": i, "out_s": round(t, 3), "luma": [round(v, 1) for v in frames]})
    return {"gate": "visual_blink", "pass": not flashes, "splices_checked": len(splices), "flashes": flashes[:20]}


def silence_gate(video: Path, run_dir: Path, max_dead_air_s: float) -> dict:
    from eddy.media.ffmpeg import FfmpegError

    try:
        lines = _detect(video, run_dir, f"silencedetect=noise=-35dB:d={max_dead_air_s}", "silence_duration", audio=True)
    except FfmpegError as e:
        return {"gate": "no_dead_air", "pass": False, "error": str(e)[:300]}
    spans = []
    for ln in lines:
        m = re.search(r"silence_duration: ([\d.]+)", ln)
        if m:
            spans.append(float(m.group(1)))
    # the natural end of a video can trail off; ignore one trailing span < 2x threshold
    bad = [s for s in spans if s > max_dead_air_s]
    if bad and len(bad) == 1 and bad[0] < 2 * max_dead_air_s:
        bad = []
    return {"gate": "no_dead_air", "pass": not bad, "spans_s": spans[:10]}


def silent_motion_gate(
    video: Path, run_dir: Path, noise_db: float, max_silence_s: float, protected_allow: int
) -> dict:
    """The 'mouth moving, no sound' guard. Run on the RENDERED output: any silent span
    longer than max_silence_s is a retained dead/false-start moment. Deliberate beats
    live inside protected moments, so we allow up to `protected_allow` such spans; one
    extra grace for a natural trailing pause. Anything beyond that FAILS — independent
    of the (advisory) judge."""
    from eddy.media.ffmpeg import FfmpegError

    try:
        lines = _detect(video, run_dir, f"silencedetect=noise={noise_db}dB:d={max_silence_s}", "silence_duration", audio=True)
    except FfmpegError as e:
        return {"gate": "silent_motion", "pass": False, "error": str(e)[:300]}
    spans = []
    for ln in lines:
        m = re.search(r"silence_duration: ([\d.]+)", ln)
        if m:
            spans.append(round(float(m.group(1)), 2))
    over = [s for s in spans if s > max_silence_s]
    allowed = protected_allow + 1  # protected beats + one trailing-pause grace
    return {
        "gate": "silent_motion",
        "pass": len(over) <= allowed,
        "spans_s": spans[:15],
        "over_count": len(over),
        "allowed": allowed,
    }


def loudness_gate(video: Path, target_lufs: float, tol: float = 2.0) -> dict:
    """Output integrated loudness within target +/- tol LUFS (post Studio Sound)."""
    from eddy.render.audio import measure_lufs

    lufs = measure_lufs(video)
    ok = lufs is not None and abs(lufs - target_lufs) <= tol
    return {"gate": "loudness", "pass": ok, "lufs": lufs, "target": target_lufs, "tol": tol}


def run_deterministic(
    video: Path,
    edl: Edl,
    run_dir: Path,
    cfg: EddyConfig,
    sim_report: dict | None = None,
    protected_count: int = 0,
    check_loudness: bool = False,
    check_visual_blink: bool = False,
) -> dict:
    gates = [
        probe_clean(video),
        av_drift(video, edl, cfg.gates.max_av_drift_s),
        black_or_frozen(video, run_dir),
        silence_gate(video, run_dir, cfg.gates.max_dead_air_s),
        silent_motion_gate(
            video, run_dir, cfg.gates.silence_noise_db, cfg.gates.max_output_silence_s, protected_count
        ),
    ]
    if check_loudness:
        gates.append(loudness_gate(video, cfg.audio.target_lufs))
    if check_visual_blink:
        gates.append(visual_blink_gate(video, edl, run_dir))
    if sim_report is not None:
        gates.append({"gate": "sim_pass", "pass": sim_report.get("pass", False)})
    return {"gates": gates, "pass": all(g["pass"] for g in gates)}


def save(report: dict, iter_dir: Path, name: str = "qa-deterministic.json") -> Path:
    p = Path(iter_dir) / name
    p.write_text(json.dumps(report, indent=1))
    return p
