"""v0.7: token + USD accounting for the paid editorial path + the per-run summary + cap source."""

from types import SimpleNamespace

import anthropic

from eddy.config import AnthropicConfig
from eddy.cost import call_cost_usd, log_cost, run_cost_summary
from eddy.providers.anthropic_api import AnthropicProvider


class _Rec:
    def __init__(self):
        self.events = []

    def log(self, event, **f):
        self.events.append((event, f))


def test_call_cost_anthropic_and_openai():
    assert call_cost_usd("anthropic", 1_000_000, 1_000_000) == round(1.0 + 5.0, 6)
    assert call_cost_usd("anthropic", 500_000, 0) == 0.5
    assert call_cost_usd("openai", 1_000_000, 0) == 0.6


def test_free_providers_cost_zero():
    for p in ("ollama", "claude_cli", "codex_cli", "unknown"):
        assert call_cost_usd(p, 1_000_000, 1_000_000) == 0.0


def test_cost_cap_hit_predicate():
    from eddy.loop.controller import _cost_cap_hit

    assert _cost_cap_hit(5.0, 5.0) is True      # at the cap -> trips
    assert _cost_cap_hit(5.01, 5.0) is True
    assert _cost_cap_hit(4.99, 5.0) is False
    assert _cost_cap_hit(1000.0, 0.0) is False  # cap 0 = unlimited


def test_log_cost_records_receipt_and_noops_without_handle():
    r = _Rec()
    log_cost(r, "openai", "gpt-x", 1000, 2000)
    ev, f = r.events[0]
    assert ev == "cost" and f["provider"] == "openai" and f["in_tok"] == 1000 and f["usd"] > 0
    log_cost(None, "openai", "x", 1, 1)  # must not raise


def test_run_cost_summary_aggregates():
    events = [
        {"event": "cost", "provider": "anthropic", "usd": 0.01, "in_tok": 100, "out_tok": 50},
        {"event": "cost", "provider": "anthropic", "usd": 0.02, "in_tok": 200, "out_tok": 80},
        {"event": "cost", "provider": "openai", "usd": 0.005, "in_tok": 50, "out_tok": 20},
        {"event": "gate", "usd": 999},  # ignored — not a cost event
    ]
    s = run_cost_summary(events)
    assert s["calls"] == 3 and s["total_usd"] == round(0.035, 4)
    assert s["by_provider"]["anthropic"] == round(0.03, 6)
    assert s["in_tok"] == 350 and s["out_tok"] == 150


def test_anthropic_provider_logs_cost_from_usage(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    rec = _Rec()

    class _Fake:
        def __init__(self, **k):
            block = SimpleNamespace(type="text", text="hello")
            usage = SimpleNamespace(input_tokens=123, output_tokens=45)
            self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[block], usage=usage))

    monkeypatch.setattr(anthropic, "Anthropic", _Fake)
    out = AnthropicProvider(AnthropicConfig(), receipts=rec).complete([{"role": "user", "content": "hi"}])
    assert out == "hello"
    cost = [f for e, f in rec.events if e == "cost"]
    assert cost and cost[0]["in_tok"] == 123 and cost[0]["out_tok"] == 45 and cost[0]["usd"] > 0
