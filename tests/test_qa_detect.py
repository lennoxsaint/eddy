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


def test_visual_blink_luma_signature():
    assert deterministic._blink_flag_from_luma(90.0, 0.5, 88.0) is True
    assert deterministic._blink_flag_from_luma(90.0, 87.0, 88.0) is False


def test_no_unauthorized_redaction_gate_fails_on_blur_metadata():
    r = deterministic.no_unauthorized_redaction_gate({"redaction": {"status": "applied"}})
    assert r["pass"] is False
    assert r["hits"][0]["key"] == "redaction"


def test_no_unauthorized_redaction_gate_can_be_explicitly_allowed():
    r = deterministic.no_unauthorized_redaction_gate(
        {"redactions": [{"x": 1, "method": "solid_cover", "opacity": 1.0}]},
        allow_redaction=True,
    )
    assert r["pass"] is True
    assert r["allowed"] is True


def test_allowed_redaction_still_fails_when_cover_is_transparent():
    r = deterministic.no_unauthorized_redaction_gate(
        {"redactions": [{"x": 1, "method": "solid_cover", "opacity": 0.94}]},
        allow_redaction=True,
    )
    assert r["pass"] is False
    assert r["opacity_failures"][0]["reason"] == "redaction_cover_not_fully_opaque"


def test_allowed_redaction_rejects_blur_as_security():
    r = deterministic.no_unauthorized_redaction_gate(
        {"redactions": [{"x": 1, "method": "gaussian_blur", "opacity": 1.0}]},
        allow_redaction=True,
    )
    assert r["pass"] is False
    assert r["opacity_failures"][0]["reason"] == "blur_is_not_secure_redaction"
