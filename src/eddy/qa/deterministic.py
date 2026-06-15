"""Hard gates on rendered artifacts. These can never be overruled by the judge."""

from __future__ import annotations

import json
import re
from pathlib import Path

from eddy.config import EddyConfig
from eddy.edit.schema import Edl
from eddy.media.probe import stream_summary


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


def _detect(video: Path, run_dir: Path, vf: str, tag: str) -> list[str]:
    """Run a -vf/af detect filter and return matching stderr lines."""
    import subprocess

    from eddy.media.ffmpeg import FFMPEG

    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(video), "-vf" if "detect" in vf and not vf.startswith("a") else "-af",
         vf, "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800,
    )
    return [ln for ln in proc.stderr.splitlines() if tag in ln]


def black_or_frozen(video: Path, run_dir: Path) -> dict:
    black = _detect(video, run_dir, "blackdetect=d=0.5:pix_th=0.10", "blackdetect")
    # screen-share content sits visually static for long stretches while the
    # creator talks — only a 60s+ freeze indicates a genuinely stuck render
    freeze = _detect(video, run_dir, "freezedetect=n=-60dB:d=60", "freeze_start")
    return {
        "gate": "black_or_frozen",
        "pass": not black and not freeze,
        "black": black[:5],
        "frozen": freeze[:5],
    }


def silence_gate(video: Path, run_dir: Path, max_dead_air_s: float) -> dict:
    lines = _detect(video, run_dir, "silencedetect=noise=-35dB:d=" + f"{max_dead_air_s}", "silence_duration")
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
    lines = _detect(video, run_dir, f"silencedetect=noise={noise_db}dB:d={max_silence_s}", "silence_duration")
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
    if sim_report is not None:
        gates.append({"gate": "sim_pass", "pass": sim_report.get("pass", False)})
    return {"gates": gates, "pass": all(g["pass"] for g in gates)}


def save(report: dict, iter_dir: Path, name: str = "qa-deterministic.json") -> Path:
    p = Path(iter_dir) / name
    p.write_text(json.dumps(report, indent=1))
    return p
