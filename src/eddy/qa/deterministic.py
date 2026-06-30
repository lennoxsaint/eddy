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
    summary = stream_summary(video)
    actual = summary["duration_s"]
    video_stream = summary.get("video") or {}
    audio_stream = summary.get("audio") or {}
    video_duration = video_stream.get("duration_s")
    audio_duration = audio_stream.get("duration_s")
    stream_drift = (
        abs(float(video_duration) - float(audio_duration))
        if video_duration is not None and audio_duration is not None
        else 0.0
    )
    rendered_vs_edl_drift = abs(actual - edl.total_duration_s)
    fps = float(video_stream.get("fps") or 30.0)
    frame_quantization_allowance = len(edl.ranges) / max(1.0, fps)
    allowed_render_drift = max(max_drift_s, frame_quantization_allowance)
    return {
        "gate": "av_drift",
        "pass": stream_drift <= max_drift_s and rendered_vs_edl_drift <= allowed_render_drift,
        "actual_s": round(actual, 2),
        "edl_s": edl.total_duration_s,
        "drift_s": round(rendered_vs_edl_drift, 2),
        "stream_drift_s": round(stream_drift, 2),
        "allowed_render_drift_s": round(allowed_render_drift, 2),
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


def _frame_luma(path: Path, roi: tuple[int, int, int, int] | None = None) -> float:
    if PILImage is None:
        raise RuntimeError("Pillow unavailable")
    img = PILImage.open(path).convert("L")
    if roi is not None:
        x, y, w, h = roi
        img = img.crop((x, y, x + w, y + h))
    img = img.resize((32, 18))
    hist = img.histogram()
    total = sum(hist) or 1
    return sum(i * c for i, c in enumerate(hist)) / total


def _splices_from_edl(edl: Edl) -> list[float]:
    splices = []
    cursor = 0.0
    for r in edl.ranges[:-1]:
        cursor += (r.end - r.start) / (r.speed or 1.0)
        splices.append(cursor)
    return splices


def visual_blink_gate(
    video: Path,
    edl: Edl,
    run_dir: Path,
    sample_window_s: float = 0.04,
    roi: tuple[int, int, int, int] | None = None,
    gate_name: str = "visual_blink",
) -> dict:
    """Sample frames around every output splice and fail if a black/white flash appears at the cut."""
    if len(edl.ranges) <= 1:
        return {"gate": gate_name, "pass": True, "splices_checked": 0, "flashes": []}
    from eddy.media.frames import extract_frame

    splices = _splices_from_edl(edl)
    out_dir = Path(run_dir) / "qa" / "blink-frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    flashes = []
    for i, t in enumerate(splices):
        frames = []
        try:
            for tag, at in (("before", t - sample_window_s), ("middle", t), ("after", t + sample_window_s)):
                p = out_dir / f"splice-{i:04d}-{tag}.jpg"
                extract_frame(video, at, p, run_dir, height=180)
                frames.append(_frame_luma(p, roi=roi))
        except Exception as e:
            return {"gate": gate_name, "pass": False, "error": str(e)[:300], "splice": i}
        if _blink_flag_from_luma(*frames):
            flashes.append({"splice": i, "out_s": round(t, 3), "luma": [round(v, 1) for v in frames]})
    return {"gate": gate_name, "pass": not flashes, "splices_checked": len(splices), "flashes": flashes[:20], "roi": roi}


def pip_blink_gate(
    video: Path,
    edl: Edl,
    run_dir: Path,
    camera_roi: tuple[int, int, int, int],
    sample_window_s: float = 0.04,
) -> dict:
    """Same blink detector, but scoped to the picture-in-picture/camera layer."""
    return visual_blink_gate(
        video,
        edl,
        run_dir,
        sample_window_s=sample_window_s,
        roi=camera_roi,
        gate_name="pip_blink",
    )


def _redaction_entries(value) -> list[dict]:
    if value in (None, False, [], {}, "none", "not_applied"):
        return []
    if isinstance(value, list):
        return [entry for item in value for entry in _redaction_entries(item)]
    if isinstance(value, dict):
        if "regions" in value:
            entries = _redaction_entries(value.get("regions"))
            return entries or [value]
        return [value]
    return [{"value": value}]


def _redaction_opacity_failures(metadata: dict) -> list[dict]:
    """Allowed privacy covers still fail if they are recoverable through transparency/blur."""
    redaction_keys = ("redaction", "redactions", "blurred_regions", "privacy_blur", "redacted")
    failures = []
    for key in redaction_keys:
        for entry in _redaction_entries(metadata.get(key)):
            method = str(entry.get("method") or entry.get("type") or "").lower()
            if "blur" in method:
                failures.append({"key": key, "reason": "blur_is_not_secure_redaction", "entry": entry})
                continue
            opacity = entry.get("opacity", entry.get("alpha", entry.get("fill_opacity")))
            if opacity is None and entry.get("solid") is True:
                continue
            if opacity is None and entry.get("method") in ("solid_cover", "opaque_cover"):
                continue
            if opacity is None:
                failures.append({"key": key, "reason": "missing_opacity_proof", "entry": entry})
                continue
            try:
                if float(opacity) < 1.0:
                    failures.append({"key": key, "reason": "redaction_cover_not_fully_opaque", "entry": entry})
            except (TypeError, ValueError):
                failures.append({"key": key, "reason": "invalid_opacity_proof", "entry": entry})
    return failures


def no_unauthorized_redaction_gate(metadata: dict | None, allow_redaction: bool = False) -> dict:
    """Fail on redaction unless allowed; allowed redaction must still be a solid cover."""
    if allow_redaction:
        failures = _redaction_opacity_failures(metadata or {})
        return {
            "gate": "no_unauthorized_redaction",
            "pass": not failures,
            "allowed": True,
            "opacity_failures": failures[:10],
        }
    md = metadata or {}
    redaction_keys = ("redaction", "redactions", "blurred_regions", "privacy_blur", "redacted")
    hits = []
    for key in redaction_keys:
        val = md.get(key)
        if val in (None, False, [], {}, "none", "not_applied"):
            continue
        hits.append({"key": key, "value": val})
    return {"gate": "no_unauthorized_redaction", "pass": not hits, "hits": hits[:10]}


def _parse_silencedetect_spans(lines: list[str]) -> list[dict]:
    spans: list[dict] = []
    current_start: float | None = None
    for ln in lines:
        start = re.search(r"silence_start: ([\d.]+)", ln)
        if start:
            current_start = float(start.group(1))
            continue
        end = re.search(r"silence_end: ([\d.]+).*silence_duration: ([\d.]+)", ln)
        if end:
            finish = float(end.group(1))
            duration = float(end.group(2))
            spans.append({
                "start": current_start if current_start is not None else finish - duration,
                "end": finish,
                "duration": duration,
            })
            current_start = None
            continue
        duration_only = re.search(r"silence_duration: ([\d.]+)", ln)
        if duration_only:
            spans.append({"start": None, "end": None, "duration": float(duration_only.group(1))})
    return spans


def _subtract_speech_from_silence(spans: list[dict], speech_spans: list[tuple[float, float]]) -> list[dict]:
    """Return silent residual pieces after expected word audio is removed.

    Studio-quality cleanup can make quiet syllables fall below ffmpeg's `silencedetect` threshold.
    A rendered-output silence gate should fail actual dead air, not low-energy words that the EDL and
    transcript say are meant to be audible.
    """
    if not speech_spans:
        return spans
    residual: list[dict] = []
    expanded_speech = [(max(0.0, s - 0.08), e + 0.08) for s, e in speech_spans]
    for sp in spans:
        start, end = sp.get("start"), sp.get("end")
        if start is None or end is None:
            residual.append(sp)
            continue
        pieces = [(float(start), float(end))]
        for ss, se in expanded_speech:
            if not pieces or se <= pieces[0][0] or ss >= pieces[-1][1]:
                continue
            next_pieces: list[tuple[float, float]] = []
            for ps, pe in pieces:
                if se <= ps or ss >= pe:
                    next_pieces.append((ps, pe))
                    continue
                if ss - ps > 0.02:
                    next_pieces.append((ps, ss))
                if pe - se > 0.02:
                    next_pieces.append((se, pe))
            pieces = next_pieces
        residual.extend({"start": ps, "end": pe, "duration": pe - ps} for ps, pe in pieces)
    return residual


def _rendered_word_spans(edl: Edl, run_dir: Path) -> list[tuple[float, float]]:
    from eddy.transcribe.whisper import words_flat

    try:
        words = words_flat(run_dir)
    except FileNotFoundError:
        return []
    out: list[tuple[float, float]] = []
    cursor = 0.0
    for r in edl.ranges:
        sp = r.speed or 1.0
        for w in words:
            start = float(w["start"])
            end = float(w["end"])
            center = (start + end) / 2
            if r.start <= center <= r.end:
                out.append((cursor + (start - r.start) / sp, cursor + (end - r.start) / sp))
        cursor += (r.end - r.start) / sp
    return out


def silence_gate(
    video: Path, run_dir: Path, max_dead_air_s: float, speech_spans: list[tuple[float, float]] | None = None
) -> dict:
    from eddy.media.ffmpeg import FfmpegError

    try:
        lines = _detect(video, run_dir, f"silencedetect=noise=-35dB:d={max_dead_air_s}", "silence_", audio=True)
    except FfmpegError as e:
        return {"gate": "no_dead_air", "pass": False, "error": str(e)[:300]}
    raw_spans = _parse_silencedetect_spans(lines)
    residual = _subtract_speech_from_silence(raw_spans, speech_spans or [])
    spans = [float(sp["duration"]) for sp in residual]
    # the natural end of a video can trail off; ignore one trailing span < 2x threshold
    bad = [s for s in spans if s > max_dead_air_s]
    if bad and len(bad) == 1 and bad[0] < 2 * max_dead_air_s:
        bad = []
    return {
        "gate": "no_dead_air",
        "pass": not bad,
        "spans_s": [round(s, 3) for s in spans[:10]],
        "raw_spans_s": [round(float(sp["duration"]), 3) for sp in raw_spans[:10]],
    }


def silent_motion_gate(
    video: Path,
    run_dir: Path,
    noise_db: float,
    max_silence_s: float,
    protected_allow: int,
    speech_spans: list[tuple[float, float]] | None = None,
) -> dict:
    """The 'mouth moving, no sound' guard. Run on the RENDERED output: any silent span
    longer than max_silence_s is a retained dead/false-start moment. Deliberate beats
    live inside protected moments, so we allow up to `protected_allow` such spans; one
    extra grace for a natural trailing pause. Anything beyond that FAILS — independent
    of the (advisory) judge."""
    from eddy.media.ffmpeg import FfmpegError

    try:
        lines = _detect(video, run_dir, f"silencedetect=noise={noise_db}dB:d={max_silence_s}", "silence_", audio=True)
    except FfmpegError as e:
        return {"gate": "silent_motion", "pass": False, "error": str(e)[:300]}
    raw_spans = _parse_silencedetect_spans(lines)
    residual = _subtract_speech_from_silence(raw_spans, speech_spans or [])
    spans = [round(float(sp["duration"]), 2) for sp in residual]
    over = [s for s in spans if s > max_silence_s]
    allowed = protected_allow + 1  # protected beats + one trailing-pause grace
    return {
        "gate": "silent_motion",
        "pass": len(over) <= allowed,
        "spans_s": spans[:15],
        "raw_spans_s": [round(float(sp["duration"]), 2) for sp in raw_spans[:15]],
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
    camera_roi: tuple[int, int, int, int] | None = None,
    render_metadata: dict | None = None,
) -> dict:
    speech_spans = _rendered_word_spans(edl, run_dir)
    gates = [
        probe_clean(video),
        av_drift(video, edl, cfg.gates.max_av_drift_s),
        black_or_frozen(video, run_dir),
        silence_gate(video, run_dir, cfg.gates.max_dead_air_s, speech_spans=speech_spans),
        silent_motion_gate(
            video,
            run_dir,
            cfg.gates.silence_noise_db,
            cfg.gates.max_output_silence_s,
            protected_count,
            speech_spans=speech_spans,
        ),
    ]
    if check_loudness:
        gates.append(loudness_gate(video, cfg.audio.target_lufs))
    if check_visual_blink:
        gates.append(visual_blink_gate(video, edl, run_dir))
    if camera_roi is not None:
        gates.append(pip_blink_gate(video, edl, run_dir, camera_roi))
    gates.append(no_unauthorized_redaction_gate(render_metadata, allow_redaction=cfg.gates.allow_redaction))
    if sim_report is not None:
        gates.extend(_sim_report_gates(sim_report))
    return {"gates": gates, "pass": all(g["pass"] for g in gates)}


def _sim_report_gates(sim_report: dict) -> list[dict]:
    """Expose creator-good simulation gates in final deterministic QA.

    The edit loop already uses the sim report to decide whether an iteration is shippable. Final QA
    should carry the same proof forward so a rendered artifact can be blocked with exact editorial
    evidence, not merely a generic "media valid" verdict.
    """
    gates: list[dict[str, object]] = [{"gate": "sim_pass", "pass": bool(sim_report.get("pass", False))}]
    for gate_name in ("retake_clean_v2", "gap_pacing", "word_onset_safety", "retake_clean"):
        gate_report = sim_report.get(gate_name)
        if isinstance(gate_report, dict) and "pass" in gate_report:
            gate: dict[str, object] = {"gate": gate_name, "pass": bool(gate_report.get("pass", False))}
            for key in ("failures", "summary", "target_s", "minimum_handle_s"):
                if key in gate_report:
                    gate[key] = gate_report[key]
            gates.append(gate)
            continue
        verdicts = sim_report.get("verdicts")
        if isinstance(verdicts, dict) and gate_name in verdicts:
            gates.append({"gate": gate_name, "pass": bool(verdicts[gate_name])})
    return gates


def save(report: dict, iter_dir: Path, name: str = "qa-deterministic.json") -> Path:
    p = Path(iter_dir) / name
    p.write_text(json.dumps(report, indent=1))
    return p
