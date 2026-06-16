"""v0.6: runtime encoder resolver. The renderer no longer hardcodes h264_videotoolbox (macOS-only);
it probes ffmpeg -encoders and prefers a HW encoder, falling back to libx264 (universal)."""

import pytest

from eddy.media import ffmpeg


def test_prefers_videotoolbox_when_present(monkeypatch):
    monkeypatch.setattr(ffmpeg, "_available_encoders", lambda: frozenset({"h264_videotoolbox", "libx264"}))
    assert ffmpeg.resolve_video_encoder() == "h264_videotoolbox"
    assert ffmpeg.video_encoder_args("7000k")[:2] == ["-c:v", "h264_videotoolbox"]
    assert "7000k" in ffmpeg.video_encoder_args("7000k")


def test_nvenc_when_no_videotoolbox(monkeypatch):
    monkeypatch.setattr(ffmpeg, "_available_encoders", lambda: frozenset({"h264_nvenc", "h264_qsv", "libx264"}))
    assert ffmpeg.resolve_video_encoder() == "h264_nvenc"  # preferred over qsv


def test_qsv_when_only_qsv_hw(monkeypatch):
    monkeypatch.setattr(ffmpeg, "_available_encoders", lambda: frozenset({"h264_qsv", "libx264"}))
    assert ffmpeg.resolve_video_encoder() == "h264_qsv"


def test_falls_back_to_libx264(monkeypatch):
    monkeypatch.setattr(ffmpeg, "_available_encoders", lambda: frozenset({"libx264"}))
    assert ffmpeg.resolve_video_encoder() == "libx264"
    args = ffmpeg.video_encoder_args()
    assert "libx264" in args and "-crf" in args and "yuv420p" in args


def test_libx264_when_nothing_detected(monkeypatch):
    monkeypatch.setattr(ffmpeg, "_available_encoders", lambda: frozenset())
    assert ffmpeg.resolve_video_encoder() == "libx264"


def test_listed_but_unrunnable_hw_encoder_is_dropped(monkeypatch):
    # nvenc compiles into most Linux/CI ffmpeg builds (so it LISTS) but can't run without a CUDA GPU
    # ("Cannot load libcuda.so.1"). _available_encoders must probe it out, or resolve picks a dead one.
    class _Fake:
        stdout = " V....D h264_nvenc          NVIDIA NVENC H.264\n V....D libx264              libx264 H.264\n"

    monkeypatch.setattr(ffmpeg.subprocess, "run", lambda *a, **k: _Fake())
    monkeypatch.setattr(ffmpeg, "_encoder_works", lambda enc: enc != "h264_nvenc")  # nvenc fails its probe
    ffmpeg._available_encoders.cache_clear()
    try:
        avail = ffmpeg._available_encoders()
        assert "libx264" in avail and "h264_nvenc" not in avail
    finally:
        ffmpeg._available_encoders.cache_clear()  # don't poison other tests' cache


@pytest.mark.needs_ffmpeg
def test_real_ffmpeg_reports_libx264(ffmpeg_required):
    enc = ffmpeg._available_encoders()
    assert "libx264" in enc  # any full ffmpeg build has it -> the fallback is real
