"""v0.5: transcription language is auto-detected by default and a forced-language mismatch (or
doubtful speech) is surfaced, not silently mistranscribed."""

import pytest

import eddy.transcribe.whisper as wm
from eddy.media.ffmpeg import FfmpegError
from eddy.runs import SourceError
from eddy.transcribe.whisper import _assert_has_speech, _language_note


def test_no_speech_fails_fast():
    with pytest.raises(SourceError, match="no speech detected"):
        _assert_has_speech([], "/x/silent.mp4")


def test_has_speech_ok():
    _assert_has_speech([{"text": "hi"}], "/x/ok.mp4")  # no raise


def test_language_match_low_no_speech_is_healthy():
    assert _language_note("en", "en", 0.1) is None


def test_auto_detect_is_healthy():
    assert _language_note(None, "fr", 0.1) is None  # no forced language -> no mismatch


def test_forced_language_mismatch_warns():
    note = _language_note("en", "es", 0.1)
    assert note is not None
    assert note["detected"] == "es" and note["requested"] == "en"
    assert any("forced language" in n for n in note["notes"])


def test_high_no_speech_probability_warns():
    note = _language_note(None, "en", 0.8)
    assert note is not None
    assert any("no-speech" in n for n in note["notes"])


def test_both_conditions_produce_two_notes():
    note = _language_note("en", "de", 0.9)
    assert len(note["notes"]) == 2


def test_no_audio_track_is_a_clear_source_error(tmp_path, monkeypatch):
    # a silent / video-only source: the audio-extract ffmpeg fails -> plain-language SourceError,
    # not a raw ffmpeg stderr dump.
    run_dir = tmp_path / "run"
    (run_dir / "transcript").mkdir(parents=True)
    monkeypatch.setattr(
        wm, "manifest",
        lambda rd: {"source_sha256": {"camera": "x"}, "sources": {"camera": "/x/silent.mp4"}},
    )

    def boom(*a, **k):
        raise FfmpegError("Output file #0 does not contain any stream")

    monkeypatch.setattr(wm, "run_ffmpeg", boom)
    with pytest.raises(SourceError, match="audio track"):
        wm.transcribe_run(run_dir)
