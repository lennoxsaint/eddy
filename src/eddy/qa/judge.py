"""Text-only editorial judge with code-side consistency checks."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.config import EddyConfig
from eddy.edit.schema import EditDecisions, Edl
from eddy.loop.receipts import Receipts
from eddy.providers.base import ProviderError

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

JUDGE_SCHEMA = {
    "type": "object",
    "required": ["defects", "scores", "summary"],
    "properties": {
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["out_s", "quote", "type", "severity", "fix_op"],
                "properties": {
                    "out_s": {"type": "number"},
                    "quote": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["bad_splice", "orphan_reference", "drag", "missing_payoff", "weak_hook", "abrupt_end"],
                    },
                    "severity": {"type": "string", "enum": ["major", "minor"]},
                    "fix_op": {
                        "type": "string",
                        "enum": ["restore", "extend_pad", "tighten_gap", "drop_beat", "swap_take", "trim_tail"],
                    },
                    "fix_note": {"type": "string"},
                },
            },
        },
        "scores": {
            "type": "object",
            "required": ["hook_integrity", "boundary_continuity", "pacing", "completeness", "ending_cta"],
            "properties": {
                k: {"type": "number"}
                for k in ("hook_integrity", "boundary_continuity", "pacing", "completeness", "ending_cta")
            },
        },
        "summary": {"type": "string"},
    },
}

WEIGHTS = {"hook_integrity": 2, "boundary_continuity": 3, "pacing": 2, "completeness": 2, "ending_cta": 1}


def weighted_score(scores: dict) -> float:
    total = sum(WEIGHTS.values())
    return round(sum(scores[k] * w for k, w in WEIGHTS.items()) / total, 2)


def evidence_packet(sim_report: dict, decisions: EditDecisions, edl: Edl, kept_phrases: list[dict]) -> str:
    beats = decisions.x_eddy.beats
    lines = []
    for p in kept_phrases:
        beat = next((b["label"] for b in beats if b.get("start_s", 0) <= p["start"] < b.get("end_s", 1e9)), "")
        lines.append(f"[{p['out_start']:.1f}] {('(' + beat + ') ') if beat else ''}{p['text']}")

    removed_big = [
        c["removed_summary"]
        for c in sim_report["boundary_cards"]
        if c["removed_s"] > 20 and c["removed_summary"]
    ]
    wpm_sections = _wpm_by_section(kept_phrases)

    stats = {
        "duration_s": sim_report["duration_s"],
        "target_s": sim_report["target_s"],
        "ranges": sim_report["ranges"],
        "removed_total_s": sim_report["removed_total_s"],
        "wpm_by_section": wpm_sections,
    }
    cards = [
        f"SPLICE @{c['splice_at_source_s']}s (removed {c['removed_s']}s):\n"
        f"  IN  …{c['before_text']}\n"
        f"  CUT [{c['removed_summary'][:160]}]\n"
        f"  OUT {c['after_text']}…"
        for c in sim_report["boundary_cards"]
    ]
    return (
        f"STATS:\n{json.dumps(stats, indent=1)}\n\n"
        f"BOUNDARY CARDS ({len(cards)}):\n" + "\n".join(cards) + "\n\n"
        f"WHAT WAS LOST (chunks >20s):\n" + "\n".join(f"- {r}" for r in removed_big[:20]) + "\n\n"
        f"CUT TRANSCRIPT:\n" + "\n".join(lines)
    )


def _wpm_by_section(kept: list[dict], sections: int = 6) -> list[int]:
    if not kept:
        return []
    end = kept[-1]["out_end"]
    out = []
    for i in range(sections):
        lo, hi = end * i / sections, end * (i + 1) / sections
        words = sum(len(p["text"].split()) for p in kept if lo <= p["out_start"] < hi)
        minutes = (hi - lo) / 60 or 1
        out.append(int(words / minutes))
    return out


def _consistent(result: dict) -> bool:
    score = weighted_score(result["scores"])
    majors = sum(1 for d in result["defects"] if d["severity"] == "major")
    if score >= 8 and majors >= 2:
        return False
    if score < 6 and majors == 0 and len(result["defects"]) == 0:
        return False
    return True


def run_judge(
    provider,
    receipts: Receipts,
    sim_report: dict,
    decisions: EditDecisions,
    edl: Edl,
    kept_phrases: list[dict],
    cfg: EddyConfig,
) -> dict:
    prompt = (PROMPTS / "judge.md").read_text()
    packet = evidence_packet(sim_report, decisions, edl, kept_phrases)
    messages = [{"role": "user", "content": f"{prompt}\n\nEVIDENCE:\n{packet}"}]

    results = []
    for attempt in range(2):
        try:
            r = provider.complete(messages, schema=JUDGE_SCHEMA, temperature=0.2, max_tokens=4096)
        except ProviderError as e:
            receipts.log("judge", ok=False, attempt=attempt, error=str(e)[:300])
            continue
        r["weighted"] = weighted_score(r["scores"])
        results.append(r)
        if _consistent(r):
            receipts.log("judge", ok=True, attempt=attempt, score=r["weighted"], defects=len(r["defects"]))
            return {**r, "judge_unstable": False}

    if not results:
        return {
            "defects": [], "scores": {k: 0 for k in WEIGHTS}, "weighted": 0.0,
            "summary": "judge unavailable", "judge_unstable": True, "advisory_only": True,
        }
    worst = min(results, key=lambda r: r["weighted"])
    receipts.log("judge", ok=True, unstable=True, score=worst["weighted"])
    return {**worst, "judge_unstable": True}
