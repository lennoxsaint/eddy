"""v0.7: face-upload consent gate (likeness) — thumbnails never upload a face without explicit
opt-in consent, even when keys are present and online."""

from eddy.config import load_config
from eddy.package.thumbnails import generate_thumbnails


class _R:
    def log(self, *a, **k):
        pass


def test_thumbnails_skip_without_consent_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("EDDY_OFFLINE", raising=False)
    cfg = load_config()
    assert cfg.thumbnails.consent_to_upload is False  # opt-in default
    out = generate_thumbnails(tmp_path, [tmp_path / "frame.jpg"], "hint", cfg, _R())
    assert out == []
    skipped = tmp_path / "final" / "thumbnails" / "thumbnails-skipped.json"
    assert skipped.exists() and "consent" in skipped.read_text()


def test_offline_still_wins_over_consent(monkeypatch, tmp_path):
    monkeypatch.setenv("EDDY_OFFLINE", "1")
    cfg = load_config()
    cfg.thumbnails.consent_to_upload = True  # even with consent, offline blocks the upload
    out = generate_thumbnails(tmp_path, [tmp_path / "frame.jpg"], "hint", cfg, _R())
    assert out == []
    assert "offline" in (tmp_path / "final" / "thumbnails" / "thumbnails-skipped.json").read_text()
