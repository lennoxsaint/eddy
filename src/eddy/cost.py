"""Token + USD accounting for the paid editorial path.

Local (ollama) and subscription CLIs (claude_cli/codex_cli) cost nothing per token, so only the
API providers (anthropic/openai) are priced. Prices are approximate $/1M tokens and intentionally
conservative (over-estimate) so a spend cap trips early rather than late.
"""

from __future__ import annotations

# approximate USD per 1M tokens (input, output). Update as pricing changes; over-estimates are safe.
PRICE_PER_MTOK = {
    "anthropic": {"input": 1.0, "output": 5.0},
    "openai": {"input": 0.6, "output": 1.8},
}


def call_cost_usd(provider: str, in_tok: int, out_tok: int) -> float:
    p = PRICE_PER_MTOK.get(provider)
    if not p:
        return 0.0  # ollama / claude_cli / codex_cli — no per-token charge
    return round((in_tok * p["input"] + out_tok * p["output"]) / 1_000_000, 6)


def log_cost(receipts, provider: str, model: str, in_tok: int, out_tok: int) -> None:
    """Log a 'cost' receipt for one paid call (no-op without a receipts handle / on free providers)."""
    if receipts is None:
        return
    receipts.log(
        "cost", provider=provider, model=model, in_tok=int(in_tok), out_tok=int(out_tok),
        usd=call_cost_usd(provider, int(in_tok), int(out_tok)),
    )


def run_cost_summary(receipts: list[dict]) -> dict:
    """Aggregate the 'cost' receipts a run logged into a total + per-provider breakdown."""
    total = 0.0
    calls = 0
    by_provider: dict[str, float] = {}
    in_tok = out_tok = 0
    for e in receipts:
        if e.get("event") != "cost":
            continue
        usd = float(e.get("usd", 0.0))
        total += usd
        calls += 1
        in_tok += int(e.get("in_tok", 0))
        out_tok += int(e.get("out_tok", 0))
        prov = e.get("provider", "?")
        by_provider[prov] = round(by_provider.get(prov, 0.0) + usd, 6)
    return {"total_usd": round(total, 4), "calls": calls, "in_tok": in_tok, "out_tok": out_tok, "by_provider": by_provider}
