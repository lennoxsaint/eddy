"""v0.5: smoke-test the synthetic media fixtures + give probe.py / the decodability preflight
real-ffmpeg coverage (previously only mocked)."""

import pytest

from eddy.media.probe import duration_s, stream_summary
from eddy.runs import SourceError, assert_sources_decodable


@pytest.mark.needs_ffmpeg
def test_tiny_camera_probes_video_and_audio(tiny_camera):
    s = stream_summary(tiny_camera)
    assert s["video"] is not None and s["audio"] is not None
    assert 1.5 < s["duration_s"] < 3.0
    assert abs(duration_s(tiny_camera) - s["duration_s"]) < 0.05


@pytest.mark.needs_ffmpeg
def test_tiny_silent_has_no_audio_stream(tiny_silent):
    assert stream_summary(tiny_silent)["audio"] is None


@pytest.mark.needs_ffmpeg
def test_webm_is_decodable(tiny_webm):
    assert stream_summary(tiny_webm)["video"] is not None


@pytest.mark.needs_ffmpeg
def test_corrupt_video_fails_preflight(corrupt_video):
    with pytest.raises(SourceError):
        assert_sources_decodable({"camera": str(corrupt_video)})


@pytest.mark.needs_ffmpeg
def test_healthy_clip_passes_preflight(tiny_camera):
    assert_sources_decodable({"camera": str(tiny_camera)})  # no raise
