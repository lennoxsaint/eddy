"""v0.5: QA detect filters route correctly (silencedetect -> -af) and a failed ffmpeg detect
FAILS the gate loud instead of silently passing. Regression for the dead-air/silent-motion
gates false-passing because silencedetect was misrouted to -vf and the non-zero exit was ignored.
"""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from eddy.media.ffmpeg import FfmpegError
from eddy.qa import deterministic


def _proc(returncode=0, stderr=""):
    return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")


def _capture(seen):
    def fake(argv, **k):
        seen["argv"] = argv
        return _proc(stderr="silence_duration: 3.0\n")
    return fake


def test_silencedetect_routes_to_af(monkeypatch):
    seen = {}
    monkeypatch.setattr(subprocess, "run", _capture(seen))
    out = deterministic._detect(Path("v.mp4"), Path("."), "silencedetect=noise=-35dB:d=2", "silence_duration", audio=True)
    assert "-af" in seen["argv"] and "-vf" not in seen["argv"]
    assert out  # the matching line is returned


def test_blackdetect_routes_to_vf(monkeypatch):
    seen = {}
    monkeypatch.setattr(subprocess, "run", _capture(seen))
    deterministic._detect(Path("v.mp4"), Path("."), "blackdetect=d=0.5", "blackdetect", audio=False)
    assert "-vf" in seen["argv"] and "-af" not in seen["argv"]


def test_detect_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: _proc(returncode=1, stderr="boom"))
    with pytest.raises(FfmpegError):
        deterministic._detect(Path("v.mp4"), Path("."), "silencedetect=x", "silence_duration", audio=True)


def test_silence_gate_fails_loud_not_false_pass(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: _proc(returncode=1, stderr="boom"))
    r = deterministic.silence_gate(Path("v.mp4"), Path("."), 2.0)
    assert r["pass"] is False and "error" in r


def test_silent_motion_gate_fails_loud(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: _proc(returncode=1, stderr="boom"))
    r = deterministic.silent_motion_gate(Path("v.mp4"), Path("."), -35.0, 2.0, 0)
    assert r["pass"] is False and "error" in r


def test_silence_gate_catches_real_dead_air(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: _proc(stderr="silence_duration: 9.0\n"))
    r = deterministic.silence_gate(Path("v.mp4"), Path("."), 2.0)
    assert r["pass"] is False  # a real 9s dead-air span now actually fails the gate
