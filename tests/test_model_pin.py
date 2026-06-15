"""v0.4: record which editorial brain produced a run (reproducibility) and warn on drift."""

import json

from eddy.config import load_config
from eddy.loop.controller import _editorial_model_id, _record_model_pin


class _Receipts:
    def __init__(self):
        self.events = []

    def log(self, event, **f):
        self.events.append((event, f))


def test_editorial_model_id_local():
    cfg = load_config()
    cfg.provider.editorial = "local"
    cfg.provider.active = "ollama"
    cfg.provider.ollama.model = "qwen36-27b-codex:q4"
    assert _editorial_model_id(cfg) == {"provider": "ollama", "model": "qwen36-27b-codex:q4"}


def test_editorial_model_id_explicit_provider():
    cfg = load_config()
    cfg.provider.editorial = "anthropic"
    cfg.provider.anthropic.model = "claude-x"
    assert _editorial_model_id(cfg) == {"provider": "anthropic", "model": "claude-x"}


def test_record_model_pin_writes_and_no_self_drift(tmp_path):
    cfg = load_config()
    cfg.provider.editorial = "local"
    cfg.provider.active = "ollama"
    r1 = _Receipts()
    _record_model_pin(tmp_path, cfg, r1)
    assert (tmp_path / "model-pin.json").exists()
    assert any(e == "model_pin" for e, _ in r1.events)
    r2 = _Receipts()
    _record_model_pin(tmp_path, cfg, r2)  # same brain on reopen
    assert not any(e == "model_drift" for e, _ in r2.events)


def test_record_model_pin_detects_drift(tmp_path):
    (tmp_path / "model-pin.json").write_text(json.dumps({"provider": "ollama", "model": "old"}))
    cfg = load_config()
    cfg.provider.editorial = "anthropic"
    cfg.provider.anthropic.model = "new"
    r = _Receipts()
    _record_model_pin(tmp_path, cfg, r)
    assert any(e == "model_drift" for e, _ in r.events)
