"""Objective audio measurement receipts: clicks, echo tail, and loudness."""

from __future__ import annotations

import json
import math
import re
import statistics
import struct
import wave
from pathlib import Path

from eddy import log
from eddy.media.ffmpeg import FFMPEG


def _read_mono_wave(wav_path: Path, max_seconds: float) -> tuple[list[float], int] | None:
    if not wav_path.exists():
        return None
    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = max(1, wf.getnchannels())
            width = wf.getsampwidth()
            rate = wf.getframerate() or 48000
            frames_to_read = min(wf.getnframes(), int(max_seconds * rate))
            raw = wf.readframes(frames_to_read)
    except Exception as exc:
        log.debug("WAV read failed for %s: %s", wav_path, exc)
        return None
    if width not in (2, 4) or not raw:
        return None
    fmt = "<" + ("h" if width == 2 else "i") * (len(raw) // width)
    try:
        vals = struct.unpack(fmt, raw)
    except struct.error:
        return None
    max_amp = float((2 ** (8 * width - 1)) - 1)
    mono = [
        sum(float(v) for v in vals[i:i + channels]) / channels / max_amp
        for i in range(0, len(vals), channels)
    ]
    return mono, rate


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(v * v for v in samples) / len(samples))


def _mouth_click_analysis(
    wav_path: Path,
    *,
    max_seconds: float = 120.0,
    bucket_s: float = 12.0,
) -> dict:
    """Return isolated transient buckets for local mouth-click receipts.

    The score is the worst local bucket, not the whole-file sum. This keeps long videos from
    saturating at 1.0 while still blocking the exact creator failure: dense wet transients in
    the hook or another local window.
    """
    read = _read_mono_wave(wav_path, max_seconds)
    if read is None:
        return {"measurable": False, "max_score": 1.0, "event_count": 0, "buckets": []}
    mono, rate = read
    if len(mono) < 4:
        return {"measurable": True, "max_score": 0.0, "event_count": 0, "buckets": []}
    jumps = [abs(mono[i] - mono[i - 1]) for i in range(1, len(mono))]
    if not jumps:
        return {"measurable": True, "max_score": 0.0, "event_count": 0, "buckets": []}
    ordered = sorted(jumps)
    median = statistics.median(ordered)
    p995 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.995))]
    adaptive = max(0.035, median * 20.0, p995 * 0.95)
    total_seconds = max(0.001, len(mono) / rate)
    bucket_seconds = max(1.0, min(bucket_s, 12.0, total_seconds))
    bucket_count = max(1, math.ceil(total_seconds / bucket_seconds))
    buckets = [
        {"start_s": idx * bucket_seconds, "duration_s": bucket_seconds, "event_count": 0, "excess": 0.0}
        for idx in range(bucket_count)
    ]
    refractory = int(rate * 0.012)
    last = -refractory
    local_radius = max(1, int(rate * 0.0015))
    width_radius = max(1, int(rate * 0.002))
    pre_radius = max(1, int(rate * 0.025))
    post_radius = max(1, int(rate * 0.065))
    total_events = 0
    for idx, jump in enumerate(jumps):
        if jump < adaptive or idx - last < refractory:
            continue
        if abs(mono[idx]) > 0.94:
            continue
        local_start = max(0, idx - local_radius)
        local_end = min(len(mono), idx + local_radius + 1)
        local = mono[local_start:local_end]
        local_peak = max(abs(v) for v in local)
        before = mono[max(0, idx - pre_radius):max(0, idx - local_radius)]
        after = mono[min(len(mono), idx + local_radius + 1):min(len(mono), idx + post_radius + 1)]
        neighbor_rms = max(_rms(before), _rms(after), 0.001)
        peak_ratio = local_peak / neighbor_rms
        if peak_ratio < 4.0:
            continue
        width = sum(
            1
            for probe in range(max(0, idx - width_radius), min(len(jumps), idx + width_radius + 1))
            if jumps[probe] >= adaptive * 0.72
        )
        if width > int(rate * 0.002):
            continue
        bucket_idx = min(bucket_count - 1, int((idx / rate) // bucket_seconds))
        buckets[bucket_idx]["event_count"] = int(buckets[bucket_idx]["event_count"]) + 1
        buckets[bucket_idx]["excess"] = float(buckets[bucket_idx]["excess"]) + (jump - adaptive)
        total_events += 1
        last = idx
    best_score = 0.0
    for bucket in buckets:
        start = float(bucket["start_s"])
        duration = max(0.001, min(bucket_seconds, total_seconds - start))
        bucket["duration_s"] = duration
        density = int(bucket["event_count"]) / duration
        score = min(1.0, density * 0.035 + float(bucket["excess"]) * 0.08)
        bucket["score"] = round(score, 5)
        bucket["excess"] = round(float(bucket["excess"]), 5)
        best_score = max(best_score, score)
    return {
        "measurable": True,
        "max_score": round(best_score, 5),
        "event_count": total_events,
        "adaptive_threshold": round(adaptive, 5),
        "buckets": buckets,
    }


def _echo_artifact_score(wav_path: Path, max_seconds: float = 120.0) -> float:
    """Approximate hollow/echo risk from post-speech tail energy.

    This is deliberately conservative: it does not pretend to be a perceptual audio judge. It gives
    Eddy a repeatable receipt that catches the failure Lennox flagged: an aggressive cleanup pass can
    reduce clicks while leaving a smeared room tail after syllables. Human listen still wins, but this
    stops obviously overcooked candidates from being selected automatically.
    """
    if not wav_path.exists():
        return 1.0
    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = max(1, wf.getnchannels())
            width = wf.getsampwidth()
            rate = wf.getframerate() or 48000
            frames_to_read = min(wf.getnframes(), int(max_seconds * rate))
            raw = wf.readframes(frames_to_read)
    except Exception as exc:
        log.debug("echo-score WAV read failed for %s (treating as worst-case): %s", wav_path, exc)
        return 1.0
    if width not in (2, 4) or not raw:
        return 1.0
    fmt = "<" + ("h" if width == 2 else "i") * (len(raw) // width)
    try:
        vals = struct.unpack(fmt, raw)
    except struct.error:
        return 1.0
    max_amp = float((2 ** (8 * width - 1)) - 1)
    mono = []
    for i in range(0, len(vals), channels):
        mono.append(sum(abs(v) for v in vals[i:i + channels]) / channels / max_amp)
    window = max(1, int(rate * 0.05))
    rms = []
    for i in range(0, len(mono), window):
        chunk = mono[i:i + window]
        if chunk:
            rms.append(math.sqrt(sum(v * v for v in chunk) / len(chunk)))
    if len(rms) < 8:
        return 0.0
    ordered = sorted(rms)
    floor = ordered[max(0, int(len(ordered) * 0.2) - 1)]
    loud = ordered[max(0, int(len(ordered) * 0.85) - 1)]
    threshold = max(floor * 4.0, loud * 0.22, 0.002)
    direct = 0.0
    tail = 0.0
    for i in range(1, len(rms) - 5):
        if rms[i] < threshold:
            continue
        if rms[i + 1] > rms[i] * 0.78:
            continue
        direct += rms[i]
        tail += sum(max(0.0, rms[j] - floor) for j in range(i + 1, i + 6))
    if direct <= 0:
        return 0.0
    return round(min(1.0, tail / (direct * 5.0)), 4)


def _click_event_count(wav_path: Path, threshold: float = 0.82, max_seconds: float = 120.0) -> int:
    """Crude local mouth-click detector: count isolated sample derivative spikes.

    This is not a perceptual model; it is an objective receipt that catches the obvious ASMR-style
    taps/clicks that survive a bad cleanup pass. A refractory window prevents one click from counting
    as hundreds of adjacent sample jumps.
    """
    if not wav_path.exists():
        return 0
    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = max(1, wf.getnchannels())
            width = wf.getsampwidth()
            rate = wf.getframerate() or 48000
            frames_to_read = min(wf.getnframes(), int(max_seconds * rate))
            raw = wf.readframes(frames_to_read)
    except Exception as exc:
        log.debug("click-count WAV read failed for %s (treating as zero clicks): %s", wav_path, exc)
        return 0
    if width not in (2, 4) or not raw:
        return 0
    fmt = "<" + ("h" if width == 2 else "i") * (len(raw) // width)
    try:
        vals = struct.unpack(fmt, raw)
    except struct.error:
        return 0
    max_amp = float((2 ** (8 * width - 1)) - 1)
    refractory = int(rate * 0.012) * channels
    last = -refractory
    count = 0
    for i in range(channels, len(vals)):
        jump = abs(vals[i] - vals[i - channels]) / max_amp
        if jump >= threshold and i - last >= refractory:
            count += 1
            last = i
    return count


def _mouth_click_score(wav_path: Path, max_seconds: float = 120.0) -> float:
    """Worst-window adaptive transient score for mouth-click risk.

    The older gate only counted very large derivative spikes, which can report zero on exactly the
    kind of smaller wet mouth clicks a creator hears immediately. This score is intentionally local:
    it looks for isolated high-derivative events relative to the file's own noise floor and reports
    the worst 12-second window, so long videos do not saturate just because they are long.
    """
    analysis = _mouth_click_analysis(wav_path, max_seconds=max_seconds, bucket_s=min(max_seconds, 12.0))
    return float(analysis["max_score"])


def _mouth_click_hotspot(wav_path: Path, *, window_s: float = 12.0, max_seconds: float = 120.0) -> dict:
    """Find a local audition window with the densest mouth-click transients."""
    analysis = _mouth_click_analysis(wav_path, max_seconds=max_seconds, bucket_s=window_s)
    if not analysis.get("measurable"):
        return {"measurable": False, "start_s": 0.0, "duration_s": window_s, "event_count": 0, "score": 1.0}
    buckets = list(analysis.get("buckets") or [])
    if not buckets:
        return {"measurable": True, "start_s": 0.0, "duration_s": window_s, "event_count": 0, "score": 0.0}
    best = max(buckets, key=lambda bucket: (float(bucket.get("score") or 0.0), int(bucket.get("event_count") or 0)))
    return {
        "measurable": True,
        "start_s": round(float(best.get("start_s") or 0.0), 3),
        "duration_s": window_s,
        "event_count": int(best.get("event_count") or 0),
        "score": float(best.get("score") or 0.0),
    }


def measure_lufs(media: Path) -> float | None:
    """Integrated loudness (LUFS) via loudnorm measurement pass. None on failure."""
    import subprocess

    # Measurement-only pass: output is `-f null -` (discarded), and a failed measure must return None
    # rather than abort the edit — so it bypasses run_ffmpeg's output-path gate and raise-on-failure.
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(media),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800,
    )
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.DOTALL)
    if not m:
        return None
    try:
        return float(json.loads(m.group(0))["input_i"])
    except (ValueError, KeyError):
        return None
