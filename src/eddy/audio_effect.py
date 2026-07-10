"""Proof that a Descript export contains a rendered effect without timing drift."""

from __future__ import annotations

import math
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

from .audio_quality import reverb_tail_metrics


@dataclass(frozen=True, slots=True)
class EffectCalibration:
    max_duration_ratio_delta: float
    max_duration_absolute_delta_s: float
    max_normalized_source_correlation: float

    @classmethod
    def default(cls) -> "EffectCalibration":
        # This is deliberately strict about unchanged/gain-only exports. It proves only that the
        # provider-applied effect survived the export round-trip; subjective quality needs listening.
        return cls(
            max_duration_ratio_delta=0.01,
            max_duration_absolute_delta_s=1.0,
            # AAC round-tripping unchanged audio measured ~0.9990 on the synthetic calibration
            # fixture, so the gate must sit below codec-only movement. A real denoise/de-reverb
            # pass moves the waveform materially farther; owner dogfoods ratchet this value only.
            max_normalized_source_correlation=0.995,
        )


@dataclass(frozen=True, slots=True)
class EffectSurvivalResult:
    passed: bool
    blockers: tuple[str, ...]
    metrics: dict[str, float]


@dataclass(frozen=True, slots=True)
class _Pcm:
    rate: int
    samples: tuple[float, ...]

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.rate


def evaluate_effect_survival(
    source_wav: Path,
    exported_wav: Path,
    calibration: EffectCalibration,
) -> EffectSurvivalResult:
    try:
        source = _read_pcm(source_wav)
        exported = _read_pcm(exported_wav)
    except (EOFError, OSError, ValueError, wave.Error):
        return EffectSurvivalResult(False, ("descript_export_invalid",), {})
    if source.rate != exported.rate:
        return EffectSurvivalResult(False, ("descript_export_sample_rate_changed",), {})

    duration_delta = abs(source.duration_s - exported.duration_s)
    duration_tolerance = max(
        calibration.max_duration_absolute_delta_s,
        source.duration_s * calibration.max_duration_ratio_delta,
    )
    lag_samples = _best_envelope_lag(source.samples, exported.samples, source.rate)
    if lag_samples >= 0:
        source_aligned = source.samples[: len(source.samples) - lag_samples or None]
        exported_aligned = exported.samples[lag_samples:]
    else:
        source_aligned = source.samples[-lag_samples:]
        exported_aligned = exported.samples[: len(exported.samples) + lag_samples or None]
    comparable = min(len(source_aligned), len(exported_aligned))
    correlation = _normalized_correlation(
        source_aligned[:comparable],
        exported_aligned[:comparable],
    )
    metrics = {
        "source_duration_s": round(source.duration_s, 6),
        "exported_duration_s": round(exported.duration_s, 6),
        "duration_delta_s": round(duration_delta, 6),
        "duration_tolerance_s": round(duration_tolerance, 6),
        "normalized_correlation": round(correlation, 8),
        "alignment_lag_s": round(lag_samples / source.rate, 6),
        "source_rms_dbfs": round(_rms_dbfs(source.samples), 4),
        "exported_rms_dbfs": round(_rms_dbfs(exported.samples), 4),
    }
    quality = reverb_tail_metrics(exported_wav)
    metrics["echo_score"] = float(quality["echo_score"])
    metrics["echo_measurable"] = 1.0 if quality["measurable"] else 0.0
    blockers: list[str] = []
    if duration_delta > duration_tolerance:
        blockers.append("descript_duration_parity_failed")
    if abs(correlation) > calibration.max_normalized_source_correlation:
        blockers.append("descript_effect_not_rendered")
    return EffectSurvivalResult(not blockers, tuple(blockers), metrics)


def _read_pcm(path: Path) -> _Pcm:
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError("effect_survival_requires_mono_pcm16")
        rate = handle.getframerate()
        if rate <= 0:
            raise ValueError("invalid_sample_rate")
        values = array("h")
        values.frombytes(handle.readframes(handle.getnframes()))
    if not values:
        raise ValueError("empty_audio")
    samples = tuple(value / 32768.0 for value in values)
    return _Pcm(rate, samples)


def _normalized_correlation(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        return 1.0
    stride = max(1, len(left) // 200_000)
    left_sampled = left[::stride]
    right_sampled = right[::stride]
    left_mean = sum(left_sampled) / len(left_sampled)
    right_mean = sum(right_sampled) / len(right_sampled)
    numerator = 0.0
    left_energy = 0.0
    right_energy = 0.0
    for left_value, right_value in zip(left_sampled, right_sampled, strict=True):
        a = left_value - left_mean
        b = right_value - right_mean
        numerator += a * b
        left_energy += a * a
        right_energy += b * b
    denominator = math.sqrt(left_energy * right_energy)
    return numerator / denominator if denominator else 1.0


def _best_envelope_lag(
    left: tuple[float, ...],
    right: tuple[float, ...],
    rate: int,
    *,
    max_lag_s: float = 2.0,
    window_ms: float = 10.0,
    max_analysis_s: float = 120.0,
) -> int:
    window = max(1, int(rate * window_ms / 1000.0))
    max_samples = int(rate * max_analysis_s)
    left_env = _rms_envelope(left[:max_samples], window)
    right_env = _rms_envelope(right[:max_samples], window)
    max_lag_windows = int(max_lag_s * rate / window)
    best_lag = 0
    best_correlation = -2.0
    for lag in range(-max_lag_windows, max_lag_windows + 1):
        if lag >= 0:
            a = left_env[: len(left_env) - lag or None]
            b = right_env[lag:]
        else:
            a = left_env[-lag:]
            b = right_env[: len(right_env) + lag or None]
        comparable = min(len(a), len(b))
        if comparable < 20:
            continue
        correlation = _normalized_correlation(a[:comparable], b[:comparable])
        if correlation > best_correlation:
            best_correlation = correlation
            best_lag = lag
    return best_lag * window


def _rms_envelope(samples: tuple[float, ...], window: int) -> tuple[float, ...]:
    envelope: list[float] = []
    for offset in range(0, len(samples) - window + 1, window):
        frame = samples[offset : offset + window]
        envelope.append(math.sqrt(sum(value * value for value in frame) / len(frame)))
    return tuple(envelope)


def _rms_dbfs(samples: tuple[float, ...]) -> float:
    if not samples:
        return -120.0
    stride = max(1, len(samples) // 200_000)
    selected = samples[::stride]
    rms = math.sqrt(sum(value * value for value in selected) / len(selected))
    return 20.0 * math.log10(max(rms, 1e-6))
