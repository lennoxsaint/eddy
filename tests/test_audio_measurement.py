"""Objective audio receipts: click counting and echo-tail scoring.

These are pure functions over a WAV file — the signal heuristics that gate which Studio Sound
candidate ships — so they're worth pinning with deterministic synthetic audio.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from eddy.render.audio import _measurement


def _write_wav(path: Path, samples: list[int], rate: int = 48000) -> Path:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return path


def _windows(amplitudes: list[float], window: int = 2400) -> list[int]:
    """Flatten per-window normalized amplitudes (0..1) into 16-bit PCM samples."""
    out: list[int] = []
    for amp in amplitudes:
        out.extend([int(amp * 32767)] * window)
    return out


# --- echo-tail score ------------------------------------------------------------------------------
def test_echo_score_missing_file_is_worst_case(tmp_path):
    assert _measurement._echo_artifact_score(tmp_path / "nope.wav") == 1.0


def test_echo_score_too_short_is_zero(tmp_path):
    # Fewer than 8 RMS windows → not enough signal to judge → 0.0 (benign).
    wav = _write_wav(tmp_path / "short.wav", _windows([0.5, 0.5]))
    assert _measurement._echo_artifact_score(wav) == 0.0


def test_echo_score_silence_is_zero(tmp_path):
    wav = _write_wav(tmp_path / "silence.wav", _windows([0.0] * 10))
    assert _measurement._echo_artifact_score(wav) == 0.0


def test_echo_score_flags_decaying_tail_over_dry_cut(tmp_path):
    # A loud burst followed by an immediate cut has no smeared tail → 0.0.
    dry = _write_wav(tmp_path / "dry.wav", _windows([0.0, 0.0, 0.8] + [0.0] * 7))
    # The same burst followed by a slow decay above the floor is the echoey failure mode.
    echoey = _write_wav(tmp_path / "echo.wav", _windows([0.0, 0.0, 0.8, 0.5, 0.35, 0.25, 0.18, 0.12, 0.0, 0.0]))
    dry_score = _measurement._echo_artifact_score(dry)
    echo_score = _measurement._echo_artifact_score(echoey)
    assert dry_score == 0.0
    assert echo_score > dry_score
    assert 0.0 <= echo_score <= 1.0


# --- click count ----------------------------------------------------------------------------------
def test_click_count_missing_file_is_zero(tmp_path):
    assert _measurement._click_event_count(tmp_path / "nope.wav") == 0


def test_click_count_silence_is_zero(tmp_path):
    assert _measurement._click_event_count(_write_wav(tmp_path / "q.wav", [0] * 48000)) == 0


def test_click_count_counts_isolated_impulses(tmp_path):
    samples = [0] * 48000
    samples[1000] = 32767
    samples[1001] = -32768  # a sharp derivative spike
    samples[20000] = 32767
    samples[20001] = -32768
    wav = _write_wav(tmp_path / "clicks.wav", samples)
    assert _measurement._click_event_count(wav, threshold=0.8) == 2


def test_click_count_refractory_collapses_adjacent_spikes(tmp_path):
    # Two spikes within the 12ms refractory window (576 samples @ 48k) count as one event.
    samples = [0] * 48000
    samples[1000] = 32767
    samples[1001] = -32768
    samples[1100] = 32767
    samples[1101] = -32768
    wav = _write_wav(tmp_path / "burst.wav", samples)
    assert _measurement._click_event_count(wav, threshold=0.8) == 1
