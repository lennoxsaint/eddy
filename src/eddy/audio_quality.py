"""Owner-calibrated speech-room metrics ported from Eddy legacy."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

ENV_FRAME_S = 0.010
BAND_LO_HZ = 300.0
BAND_HI_HZ = 4000.0


def reverb_tail_metrics(wav_path: Path, max_seconds: float = 120.0) -> dict[str, Any]:
    read = _read_mono(wav_path, max_seconds)
    if read is None:
        return {"measurable": False, "reason": "unreadable", "echo_score": 1.0}
    samples, rate = read
    if len(samples) < rate * 3:
        return {"measurable": False, "reason": "too_short", "echo_score": 0.0}
    env = _envelope_db(_bandpass_fft(samples, rate), rate)
    if len(env) < 100:
        return {"measurable": False, "reason": "too_short", "echo_score": 0.0}
    floor = max(float(np.percentile(env, 10)), -85.0)
    speech = float(np.percentile(env, 90))
    if speech - floor < 15.0:
        return {"measurable": False, "reason": "low_dynamic_contrast", "echo_score": 0.0}

    on_threshold = speech - 12.0
    off_threshold = speech - 18.0
    hold = int(0.30 / ENV_FRAME_S)
    lag_150 = int(0.150 / ENV_FRAME_S)
    offset_tails: list[float] = []
    index = 0
    while index < len(env) - hold - lag_150:
        if env[index] >= on_threshold and env[index + 1] < off_threshold:
            segment = env[index + 1 : index + 1 + hold]
            if len(segment) == hold and bool(np.all(segment < on_threshold)):
                offset_tails.append(max(0.0, float(env[index + lag_150]) - floor))
                index += hold
                continue
        index += 1

    count = len(env)
    speech_active = env > (speech - 14.0)
    quiet = env < (speech - 22.0)
    active_indexes = np.flatnonzero(speech_active)
    tail_zone = np.zeros(count, dtype=bool)
    recent = np.zeros(count, dtype=bool)
    far = np.ones(count, dtype=bool)
    low_lookback = int(0.100 / ENV_FRAME_S)
    high_lookback = int(0.400 / ENV_FRAME_S)
    spill = int(0.060 / ENV_FRAME_S)
    far_guard = int(0.600 / ENV_FRAME_S)
    for active in active_indexes:
        low = active + low_lookback
        if low < count:
            tail_zone[low : min(count, active + high_lookback)] = True
        recent[active : min(count, active + spill)] = True
        far[active : min(count, active + far_guard)] = False
    tail_quiet = tail_zone & quiet & ~speech_active & ~recent
    far_quiet = far & quiet
    room_excess = None
    if int(tail_quiet.sum()) >= 20 and int(far_quiet.sum()) >= 20:
        tail_median = float(np.median(env[tail_quiet] - floor))
        ambient = float(np.median(env[far_quiet] - floor))
        room_excess = max(0.0, tail_median - ambient)
    offset_tail = float(np.median(offset_tails)) if len(offset_tails) >= 3 else None
    if offset_tail is None and room_excess is None:
        return {"measurable": False, "reason": "no_valid_component", "echo_score": 0.0}
    components: list[float] = []
    if offset_tail is not None:
        components.append(min(1.0, offset_tail / 25.0))
    if room_excess is not None:
        components.append(min(1.0, room_excess / 12.0))
    return {
        "measurable": True,
        "echo_score": round(float(sum(components) / len(components)), 4),
        "offset_tail_above_floor_db": round(offset_tail, 1) if offset_tail is not None else None,
        "room_excess_db": round(room_excess, 1) if room_excess is not None else None,
        "floor_db": round(floor, 1),
        "speech_db": round(speech, 1),
    }


def _read_mono(path: Path, max_seconds: float) -> tuple[NDArray[np.float64], int] | None:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = max(1, handle.getnchannels())
            width = handle.getsampwidth()
            rate = handle.getframerate() or 48_000
            raw = handle.readframes(min(handle.getnframes(), int(max_seconds * rate)))
    except (EOFError, OSError, wave.Error):
        return None
    if width not in (2, 4) or not raw:
        return None
    dtype = np.int16 if width == 2 else np.int32
    usable = (len(raw) // (width * channels)) * width * channels
    samples = np.frombuffer(raw[:usable], dtype=dtype).astype(np.float64)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    samples /= float(2 ** (8 * width - 1) - 1)
    return samples, int(rate)


def _bandpass_fft(samples: NDArray[np.float64], rate: int) -> NDArray[np.float64]:
    count = len(samples)
    padded = 1 << max(4, (count - 1).bit_length())
    spectrum = np.fft.rfft(samples, n=padded)
    frequencies = np.fft.rfftfreq(padded, 1.0 / rate)
    spectrum[(frequencies < BAND_LO_HZ) | (frequencies > BAND_HI_HZ)] = 0
    return np.asarray(np.fft.irfft(spectrum, n=padded)[:count], dtype=np.float64)


def _envelope_db(samples: NDArray[np.float64], rate: int) -> NDArray[np.float64]:
    frame_size = max(1, int(rate * ENV_FRAME_S))
    usable = (len(samples) // frame_size) * frame_size
    if usable == 0:
        return np.array([], dtype=np.float64)
    frames = samples[:usable].reshape(-1, frame_size)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    return np.asarray(20.0 * np.log10(rms + 1e-10), dtype=np.float64)
