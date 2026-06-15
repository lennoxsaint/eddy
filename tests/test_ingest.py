"""v0.5: broader format acceptance + a decodability preflight so corrupt/unsupported input fails
loud with an actionable message instead of crashing mid-pipeline."""

import pytest

from eddy.runs import AUDIO_EXTS, VIDEO_EXTS, SourceError, assert_sources_decodable, discover_sources


def test_video_exts_includes_common_formats():
    for ext in (".webm", ".avi", ".ts", ".mts", ".wmv", ".flv", ".3gp"):
        assert ext in VIDEO_EXTS


def test_discover_accepts_webm(tmp_path):
    v = tmp_path / "clip.webm"
    v.write_bytes(b"x")
    assert discover_sources(v) == {"camera": v}


def _summary(video=None, dur=30.0):
    return {"video": video, "audio": {}, "duration_s": dur}


def test_decodable_passes_healthy(monkeypatch):
    monkeypatch.setattr("eddy.media.probe.stream_summary", lambda p: _summary(video={"width": 1920}))
    assert_sources_decodable({"camera": "/x/cam.mp4"})  # no raise


def test_decodable_raises_on_no_video_stream(monkeypatch):
    monkeypatch.setattr("eddy.media.probe.stream_summary", lambda p: _summary(video=None))
    with pytest.raises(SourceError, match="no decodable video"):
        assert_sources_decodable({"camera": "/x/cam.mp4"})


def test_decodable_raises_on_zero_duration_camera(monkeypatch):
    monkeypatch.setattr("eddy.media.probe.stream_summary", lambda p: _summary(video={"width": 1}, dur=0.0))
    with pytest.raises(SourceError, match="duration"):
        assert_sources_decodable({"camera": "/x/cam.mp4"})


def test_decodable_raises_on_zero_duration_screen(monkeypatch):
    # the preflight checks EVERY video source's duration, not just camera
    monkeypatch.setattr(
        "eddy.media.probe.stream_summary",
        lambda p: _summary(video={"width": 1}, dur=(0.0 if "screen" in str(p) else 30.0)),
    )
    with pytest.raises(SourceError, match="duration"):
        assert_sources_decodable({"camera": "/x/cam.mp4", "screen": "/x/screen.mp4"})


def test_decodable_raises_on_probe_error(monkeypatch):
    def boom(p):
        raise RuntimeError("ffprobe exploded")

    monkeypatch.setattr("eddy.media.probe.stream_summary", boom)
    with pytest.raises(SourceError, match="cannot decode"):
        assert_sources_decodable({"camera": "/x/bad.mp4"})


def test_decodable_skips_mic(monkeypatch):
    seen = []
    monkeypatch.setattr("eddy.media.probe.stream_summary",
                        lambda p: seen.append(str(p)) or _summary(video={"w": 1}))
    assert_sources_decodable({"camera": "/x/cam.mp4", "mic": "/x/mic.wav"})
    assert "/x/mic.wav" not in seen  # audio-only mic isn't checked for a video stream


# v0.8: audio-first ingest — podcasters can `eddy transcribe` an .mp3/.wav, and `eddy run` on
# audio fails with a transcribe hint instead of a cryptic "no video stream".


def test_audio_exts_includes_common_formats():
    for ext in (".mp3", ".wav", ".m4a", ".flac", ".aac"):
        assert ext in AUDIO_EXTS


def test_discover_accepts_audio_file(tmp_path):
    a = tmp_path / "episode.mp3"
    a.write_bytes(b"x")
    assert discover_sources(a) == {"camera": a}  # transcribe reads the "camera" source


def test_discover_still_rejects_non_media(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_bytes(b"x")
    with pytest.raises(SourceError, match="not a video/audio file"):
        discover_sources(f)


def test_run_on_audio_hints_transcribe(monkeypatch):
    monkeypatch.setattr("eddy.media.probe.stream_summary", lambda p: _summary(video=None))
    with pytest.raises(SourceError, match="audio-only.*transcribe"):
        assert_sources_decodable({"camera": "/x/episode.mp3"})
