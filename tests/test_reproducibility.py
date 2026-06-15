"""v1.0 GA: reproducibility. Tier 1 (deterministic core) is byte-reproducible; Tier 2 (local brain)
gains an EXACT mode via a pinned sampler seed. These prove the seed plumbing + EDL stability without
needing a real model."""

from pathlib import Path

from eddy.config import OllamaConfig
from eddy.providers.ollama import OllamaProvider


class _Resp:
    status_code = 200

    def json(self):
        return {"message": {"content": "ok"}}


def _capture_post(captured):
    def post(url, json=None, timeout=None):  # noqa: A002 - mirrors httpx.post signature
        captured["body"] = json
        return _Resp()

    return post


def test_seed_sent_to_ollama_when_configured(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr("eddy.providers.ollama.httpx.post", _capture_post(captured))
    prov = OllamaProvider(OllamaConfig(seed=42, temperature=0.0))
    prov.complete([{"role": "user", "content": "hi"}])
    assert captured["body"]["options"]["seed"] == 42
    assert captured["body"]["options"]["temperature"] == 0.0


def test_seed_absent_when_unset(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr("eddy.providers.ollama.httpx.post", _capture_post(captured))
    prov = OllamaProvider(OllamaConfig())  # default: no seed
    prov.complete([{"role": "user", "content": "hi"}])
    assert "seed" not in captured["body"]["options"]  # quality mode: not pinned


def test_edl_compilation_is_byte_reproducible():
    # Tier 1: the same decisions compile to a byte-identical EDL every time.
    from eddy.config import EddyConfig
    from eddy.edit.compiler import compile_edl
    from eddy.edit.schema import EditDecisions

    cfg = EddyConfig()
    words = [{"start": i * 1.0, "end": i * 1.0 + 0.9, "word": f" w{i}", "probability": 0.9} for i in range(20)]
    decisions = EditDecisions(retakes=[], cuts=[], protected_moments=[], shorts_candidates=[])
    kw = dict(words=words, source_path="/x/cam.mp4", duration_s=20.0, render_cfg=cfg.render, gates_cfg=cfg.gates)
    a = compile_edl(decisions, **kw)
    b = compile_edl(decisions, **kw)
    assert a.model_dump_json() == b.model_dump_json()


def test_reproducibility_doc_present():
    doc = (Path(__file__).resolve().parent.parent / "docs" / "REPRODUCIBILITY.md").read_text().lower()
    for needle in ("deterministic", "seed", "temperature = 0", "golden suite", "digest"):
        assert needle in doc
