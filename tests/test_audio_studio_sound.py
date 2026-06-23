from eddy.config import AudioConfig
from eddy.render import audio


def test_speech_eq_includes_local_studio_sound_cleanup_when_filters_exist(monkeypatch):
    monkeypatch.setattr(
        audio,
        "_available_audio_filters",
        lambda: frozenset({"afftdn", "adeclick", "deesser", "acompressor"}),
    )
    chain = audio._speech_eq(AudioConfig())
    assert "afftdn" in chain
    assert "adeclick" in chain
    assert "deesser" in chain
    assert "acompressor" in chain
    assert "alimiter" in chain


def test_speech_eq_skips_optional_filters_portably(monkeypatch):
    monkeypatch.setattr(audio, "_available_audio_filters", lambda: frozenset())
    chain = audio._speech_eq(AudioConfig())
    assert "highpass" in chain
    assert "equalizer" in chain
    assert "alimiter" in chain
    assert "adeclick" not in chain
