"""v0.5: transcription language is auto-detected by default and a forced-language mismatch (or
doubtful speech) is surfaced, not silently mistranscribed."""

from eddy.transcribe.whisper import _language_note


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
