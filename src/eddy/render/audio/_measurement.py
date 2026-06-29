"""Objective audio measurement receipts: clicks, echo tail, and loudness."""

from __future__ import annotations

import json
import re
import wave
from pathlib import Path

from eddy import log
from eddy.media.ffmpeg import FFMPEG


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
    import math
    import struct

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
    import struct

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
    """Adaptive transient score for mouth-click risk.

    The older gate only counted very large derivative spikes, which can report zero on exactly the
    kind of smaller wet mouth clicks a creator hears immediately. This score is intentionally simple
    and local: it looks for isolated high-derivative events relative to the file's own noise floor.
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
        log.debug("mouth-click WAV read failed for %s (treating as worst-case): %s", wav_path, exc)
        return 1.0
    if width not in (2, 4) or not raw:
        return 1.0
    import statistics
    import struct

    fmt = "<" + ("h" if width == 2 else "i") * (len(raw) // width)
    try:
        vals = struct.unpack(fmt, raw)
    except struct.error:
        return 1.0
    max_amp = float((2 ** (8 * width - 1)) - 1)
    mono: list[float] = []
    for i in range(0, len(vals), channels):
        mono.append(sum(float(v) for v in vals[i:i + channels]) / channels / max_amp)
    if len(mono) < 4:
        return 0.0
    jumps = [abs(mono[i] - mono[i - 1]) for i in range(1, len(mono))]
    if not jumps:
        return 0.0
    ordered = sorted(jumps)
    median = statistics.median(ordered)
    p99 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))]
    adaptive = max(0.025, median * 12.0, p99 * 0.62)
    refractory = int(rate * 0.010)
    last = -refractory
    events = 0
    total_excess = 0.0
    for idx, jump in enumerate(jumps):
        if jump < adaptive or idx - last < refractory:
            continue
        # Mouth clicks are short transients; ignore full-scale clipping/screams as a different defect.
        local_amp = abs(mono[idx])
        if local_amp > 0.92:
            continue
        events += 1
        total_excess += jump - adaptive
        last = idx
    seconds = max(0.001, len(mono) / rate)
    density = events / seconds
    return round(min(1.0, density * 0.035 + total_excess * 0.08), 5)


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
