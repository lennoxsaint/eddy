"""v0.4 privacy honesty: --local-only / EDDY_OFFLINE makes 'nothing leaves your machine' true —
forces the local brain, skips the cloud thumbnail path. (Whisper local_files_only is covered by
the offline flag threading; not unit-tested here to avoid downloading weights.)"""

from eddy.config import load_config
from eddy.package.thumbnails import generate_thumbnails
from eddy.privacy import is_offline
from eddy.providers.base import get_editorial_provider


class _R:
    def log(self, *a, **k):
        pass


def test_is_offline_reads_env(monkeypatch):
    monkeypatch.delenv("EDDY_OFFLINE", raising=False)
    assert is_offline() is False
    monkeypatch.setenv("EDDY_OFFLINE", "1")
    assert is_offline() is True
    monkeypatch.setenv("EDDY_OFFLINE", "true")
    assert is_offline() is True
    monkeypatch.setenv("EDDY_OFFLINE", "")
    assert is_offline() is False


def test_offline_forces_local_brain_over_explicit_cloud(monkeypatch):
    monkeypatch.setenv("EDDY_OFFLINE", "1")
    cfg = load_config()
    cfg.provider.editorial = "anthropic"  # explicit cloud, but offline must override
    cfg.provider.active = "ollama"
    prov = get_editorial_provider(cfg, receipts=None)
    assert prov.name == "ollama"  # local, not a FallbackProvider to the cloud


def test_auto_brain_not_forced_local_when_online(monkeypatch):
    monkeypatch.delenv("EDDY_OFFLINE", raising=False)
    cfg = load_config()
    cfg.provider.editorial = "local"
    cfg.provider.active = "ollama"
    # editorial='local' returns the local brain even online — sanity that the offline branch
    # didn't change the normal local path.
    assert get_editorial_provider(cfg, receipts=None).name == "ollama"


def test_thumbnails_skipped_when_offline(monkeypatch, tmp_path):
    monkeypatch.setenv("EDDY_OFFLINE", "1")
    cfg = load_config()
    out = generate_thumbnails(tmp_path, [tmp_path / "frame.jpg"], "hint", cfg, _R())
    assert out == []
    skipped = tmp_path / "final" / "thumbnails" / "thumbnails-skipped.json"
    assert skipped.exists() and "offline" in skipped.read_text()
