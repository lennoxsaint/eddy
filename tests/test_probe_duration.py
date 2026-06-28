"""v0.5: crash-proof duration resolution. format.duration -> longest stream.duration -> unknown,
never a KeyError/ValueError on a container that omits or 'N/A's the duration."""

from pathlib import Path

import pytest

from eddy.media import probe
from eddy.media.ffmpeg import FfmpegError
from eddy.media.probe import _resolve_duration, duration_s, eval_fps, stream_summary


def test_eval_fps_handles_null_and_garbage():
    assert eval_fps(None) == 0.0      # ffprobe avg_frame_rate: null must not crash
    assert eval_fps("0/0") == 0.0
    assert eval_fps("30/1") == 30.0
    assert eval_fps("garbage") == 0.0


def test_stream_summary_handles_null_fps(monkeypatch):
    monkeypatch.setattr(probe, "probe", lambda p: {
        "format": {"duration": "10"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": None,
                "duration": "9.9",
            }
        ],
    })
    video = stream_summary(Path("x.mp4"))["video"]
    assert video["fps"] == 0.0  # null fps -> 0.0, no crash
    assert video["duration_s"] == 9.9


def test_resolve_prefers_format_duration():
    assert _resolve_duration({"format": {"duration": "12.5"}, "streams": []}) == 12.5


def test_resolve_falls_back_to_longest_stream():
    info = {"format": {}, "streams": [{"duration": "3.0"}, {"duration": "9.5"}, {"duration": "N/A"}]}
    assert _resolve_duration(info) == 9.5


def test_resolve_unknown_is_zero_not_crash():
    assert _resolve_duration({"format": {"duration": "N/A"}, "streams": [{}]}) == 0.0
    assert _resolve_duration({}) == 0.0  # missing format AND streams


def test_duration_s_fails_loud_when_unknown(monkeypatch):
    monkeypatch.setattr(probe, "probe", lambda p: {"format": {"duration": "N/A"}, "streams": []})
    with pytest.raises(FfmpegError, match="could not determine duration"):
        duration_s(Path("x.mp4"))


def test_stream_summary_tolerates_missing_format_and_streams(monkeypatch):
    monkeypatch.setattr(probe, "probe", lambda p: {})  # no format, no streams
    s = stream_summary(Path("x.mp4"))
    assert s["duration_s"] == 0.0 and s["video"] is None and s["audio"] is None


def test_stream_summary_handles_na_sample_rate(monkeypatch):
    monkeypatch.setattr(probe, "probe", lambda p: {
        "format": {"duration": "10"},
        "streams": [
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "N/A", "channels": 2, "duration": "9.8"}
        ],
    })
    s = stream_summary(Path("x.mp4"))
    assert s["audio"]["sample_rate"] == 0 and s["audio"]["channels"] == 2
    assert s["audio"]["duration_s"] == 9.8
