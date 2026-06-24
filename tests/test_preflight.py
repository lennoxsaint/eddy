"""v0.6: doctor environment preflight + `eddy run --dry-run` so problems surface BEFORE a 20GB
model pull + a 50-min transcribe, not as a cryptic mid-run crash."""

import pytest
from typer.testing import CliRunner

from eddy.cli import app
from eddy.doctor import _ffmpeg_major, preflight

runner = CliRunner()


def test_ffmpeg_major_parser():
    assert _ffmpeg_major("ffmpeg version 8.0 Copyright (c) ...") == 8
    assert _ffmpeg_major("ffmpeg version n6.1.1 ...") == 6
    assert _ffmpeg_major("ffmpeg version 7.0.2-static https://...") == 7
    assert _ffmpeg_major("not a version line") is None


@pytest.mark.needs_ffmpeg
def test_preflight_passes_on_this_machine(ffmpeg_required):
    checks = {c["check"]: c for c in preflight()}
    assert checks["ffmpeg"]["ok"]
    assert checks["ffprobe"]["ok"]
    assert checks["video encoder"]["ok"]


@pytest.mark.needs_ffmpeg
def test_dry_run_ok_on_good_clip(tiny_camera, monkeypatch):
    # This test is about source decodability. The real environment preflight is covered above;
    # CI intentionally does not install the heavy Studio Sound backend.
    monkeypatch.setattr(
        "eddy.doctor.preflight",
        lambda: [
            {"check": "ffmpeg", "ok": True, "detail": "v8"},
            {"check": "ffprobe", "ok": True, "detail": "found"},
            {"check": "video encoder", "ok": True, "detail": "libx264"},
            {"check": "studio sound", "ok": True, "detail": "test stub"},
            {"check": "free disk", "ok": True, "detail": "test stub"},
        ],
    )
    r = runner.invoke(app, ["run", str(tiny_camera), "--dry-run"])
    assert r.exit_code == 0
    assert "ready to run" in r.output


@pytest.mark.needs_ffmpeg
def test_dry_run_fails_on_corrupt_source(corrupt_video, monkeypatch):
    monkeypatch.setattr(
        "eddy.doctor.preflight",
        lambda: [
            {"check": "ffmpeg", "ok": True, "detail": "v8"},
            {"check": "ffprobe", "ok": True, "detail": "found"},
            {"check": "video encoder", "ok": True, "detail": "libx264"},
            {"check": "studio sound", "ok": True, "detail": "test stub"},
            {"check": "free disk", "ok": True, "detail": "test stub"},
        ],
    )
    r = runner.invoke(app, ["run", str(corrupt_video), "--dry-run"])
    assert r.exit_code == 1
    assert "problems found" in r.output


@pytest.mark.needs_ffmpeg
def test_dry_run_fails_when_studio_sound_preflight_fails(tiny_camera, monkeypatch):
    monkeypatch.setattr(
        "eddy.doctor.preflight",
        lambda: [
            {"check": "ffmpeg", "ok": True, "detail": "v8"},
            {"check": "ffprobe", "ok": True, "detail": "found"},
            {"check": "video encoder", "ok": True, "detail": "libx264"},
            {"check": "studio sound", "ok": False, "detail": "missing backend"},
            {"check": "free disk", "ok": True, "detail": "test stub"},
        ],
    )

    r = runner.invoke(app, ["run", str(tiny_camera), "--dry-run"])

    assert r.exit_code == 1
    assert "studio sound" in r.output
    assert "problems found" in r.output
