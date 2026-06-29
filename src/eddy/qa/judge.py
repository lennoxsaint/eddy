"""Text-only editorial judge with code-side consistency checks."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.config import EddyConfig
from eddy.edit.schema import EditDecisions, Edl
from eddy.loop.receipts import Receipts
from eddy.providers.base import ProviderError
from eddy.safety import fence

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

# v0.3: pacing raised 2→3 (ties boundary as the heaviest) — a too-long, drag-heavy cut must
# no longer be able to score well on the strength of the other dimensions alone.
WEIGHTS = {"hook_integrity": 2, "boundary_continuity": 3, "pacing": 3, "completeness": 2, "ending_cta": 1}


def weighted_score(scores: dict) -> float:
    total = sum(WEIGHTS.values())
    if not isinstance(scores, dict):
        return 0.0

    def _dim(k: str) -> float:
        # clamp each dimension to the rubric's 1-10 so an out-of-range model score (e.g. 50)
        # cannot blow the weighted average past the 8.0 ship gate; a missing dimension defaults
        # to 1 (worst) so a malformed judge can't omit a low score to inflate the result.
        try:
            v = float(scores.get(k, 1))
        except (TypeError, ValueError):
            v = 1.0
        return min(10.0, max(1.0, v))

    return round(sum(_dim(k) * w for k, w in WEIGHTS.items()) / total, 2)


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
    visual_inserts = []
    for note in getattr(decisions, "visual_insert_notes", []) or []:
        if not isinstance(note, dict):
            continue
        text = str(note.get("text") or note.get("note") or note.get("title") or "").strip()
        if not text:
            continue
        start = note.get("out_start_s", note.get("start_s", note.get("at_s", "?")))
        end = note.get("out_end_s", note.get("end_s", "?"))
        visual_inserts.append(f"[{start}–{end}] {text[:220]}")
    return (
        f"STATS:\n{json.dumps(stats, indent=1)}\n\n"
        f"BOUNDARY CARDS ({len(cards)}):\n" + "\n".join(cards) + "\n\n"
        f"VISUAL INSERTS ({len(visual_inserts)}):\n"
        + ("\n".join(f"- {v}" for v in visual_inserts) if visual_inserts else "- none")
        + "\n\n"
        "WHAT WAS LOST (chunks >20s):\n" + "\n".join(f"- {r}" for r in removed_big[:20]) + "\n\n"
        + fence("CUT TRANSCRIPT", "\n".join(lines))
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


def _focus_judge_context(focus: str | None, focus_mode: str | None) -> str:
    """Brief-aware judging. A focus/extract edit must be scored against the user's FOCUS BRIEF, not
    against the standalone-video conventions this rubric assumes (hook/completeness/CTA) that an
    extract deliberately breaks. Returns '' for a normal edit (judge prompt unchanged)."""
    if not focus or not focus.strip():
        return ""
    focus = focus.strip()
    if focus_mode == "extract":
        body = (
            "This edit is a TOPICAL EXTRACT, not a standalone video. The editor's brief was:\n"
            f"  {focus}\n"
            "Judge boundary_continuity and pacing NORMALLY — a severed thought, a glued splice, or a "
            "drag is still a real defect, and a fragmented 'stitched from many slivers' feel is a "
            "MAJOR boundary_continuity defect. But do NOT penalize hook_integrity, completeness, or "
            "ending_cta for the absence of standalone-video conventions: an extract legitimately opens "
            "mid-context, omits the off-topic setup/tangents/payoff that were cut on purpose, and ends "
            "at the topic boundary with no CTA. Score completeness on whether the KEPT topic is "
            "internally whole — a promise made INSIDE the kept span left unpaid — not on whether the "
            "original video's full arc survives. A clean stop at the end of the topic is ending_cta 10, "
            "not abrupt_end. Off-topic material that was correctly removed is never a missing_payoff or "
            "an orphan_reference."
        )
    else:
        body = (
            "The editor steered this edit toward a FOCUS BRIEF:\n"
            f"  {focus}\n"
            "Bias completeness and pacing toward how well the kept content serves this brief. Tangents "
            "cut because they don't serve the brief are NOT defects — do not ask for them back."
        )
    return f"FOCUS CONTEXT (read before scoring):\n{body}\n\n"


def _consistent(result: dict) -> bool:
    score = weighted_score(result.get("scores", {}))
    defects = result.get("defects") or []
    majors = sum(1 for d in defects if isinstance(d, dict) and d.get("severity") == "major")
    if score >= 8 and majors >= 2:
        return False
    if score < 6 and majors == 0 and len(defects) == 0:
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
    focus: str | None = None,
    focus_mode: str | None = None,
) -> dict:
    prompt = (PROMPTS / "judge.md").read_text()
    packet = evidence_packet(sim_report, decisions, edl, kept_phrases)
    focus_ctx = _focus_judge_context(focus, focus_mode)
    messages = [{"role": "user", "content": f"{prompt}\n\n{focus_ctx}EVIDENCE:\n{packet}"}]

    results = []
    for attempt in range(2):
        try:
            r = provider.complete(messages, schema=JUDGE_SCHEMA, temperature=0.2, max_tokens=4096)
            if not isinstance(r, dict):
                raise TypeError(f"judge returned {type(r).__name__}, expected object")
            # process INSIDE the try: a structurally-malformed-but-returned judge (missing
            # scores, wrong types) must degrade to a skipped attempt, not abort the whole run.
            r.setdefault("defects", [])
            r.setdefault("scores", {})
            r.setdefault("summary", "")
            r["weighted"] = weighted_score(r["scores"])
        except (ProviderError, KeyError, TypeError, ValueError) as e:
            receipts.log("judge", ok=False, attempt=attempt, error=str(e)[:300])
            continue
        results.append(r)
        if _consistent(r):
            receipts.log("judge", ok=True, attempt=attempt, score=r["weighted"], defects=len(r["defects"]))
            return {**r, "judge_unstable": False}

    if not results:
        # v0.3: an unavailable judge returns weighted 0 and judge_unstable — it must NOT
        # certify "done" (the old advisory_only auto-pass is gone; the loop gates on
        # `not judge_unstable`, and quality caps an unstable critic at 5).
        return {
            "defects": [], "scores": {k: 0 for k in WEIGHTS}, "weighted": 0.0,
            "summary": "judge unavailable", "judge_unstable": True,
        }
    worst = min(results, key=lambda r: r["weighted"])
    receipts.log("judge", ok=True, unstable=True, score=worst["weighted"])
    return {**worst, "judge_unstable": True}


# --- v0.3 final-ship panel: 3 independent lenses, majority ships ----------------------------

PANEL_SCHEMA = {
    "type": "object",
    "required": ["ship", "reason"],
    "properties": {"ship": {"type": "boolean"}, "reason": {"type": "string"}},
}

SHIP_LENSES = {
    "pacing": "You judge ONE thing: does this edit DRAG? Ignore splices and continuity. A demanding "
              "viewer's time is precious — if any stretch is slow, list-reading, or over-long, do not ship.",
    "continuity": "You judge ONE thing: splices and orphans. Ignore pacing. If any cut sounds glued, "
                  "a setup is orphaned from its payoff, or a reference dangles, do not ship.",
    "taste": "You judge ONE thing: is this worth a stranger's time end to end — strong hook, the promise "
             "paid off, a clean ending? If it opens weak or trails off, do not ship.",
}


def run_ship_panel(provider, receipts: Receipts, sim_report: dict, decisions: EditDecisions,
                   edl: Edl, kept_phrases: list[dict], cfg: EddyConfig,
                   focus: str | None = None, focus_mode: str | None = None) -> dict:
    """Run ONCE on the chosen best iteration: 3 independent lenses each vote ship/no-ship,
    majority decides. Advisory — never blocks delivery in v0.3 (records dissent)."""
    packet = evidence_packet(sim_report, decisions, edl, kept_phrases)
    focus_ctx = _focus_judge_context(focus, focus_mode)
    votes = []
    for lens, framing in SHIP_LENSES.items():
        msg = [{"role": "user", "content":
                f"You are a hostile, skeptical release reviewer. Default: NOT ready.\n{framing}\n\n"
                f"{focus_ctx}EVIDENCE:\n{packet}"}]
        try:
            r = provider.complete(msg, schema=PANEL_SCHEMA, temperature=0.2, max_tokens=512)
            votes.append({"lens": lens, "ship": bool(r.get("ship")), "reason": r.get("reason", "")[:200]})
        except ProviderError as e:
            receipts.log("ship_panel_lens", lens=lens, ok=False, error=str(e)[:200])
            votes.append({"lens": lens, "ship": False, "reason": f"lens unavailable: {str(e)[:80]}"})
    ship_yes = sum(1 for v in votes if v["ship"])
    ships = ship_yes >= (len(votes) // 2 + 1)
    receipts.log("ship_panel", ships=ships, yes=ship_yes, of=len(votes))
    return {"ships": ships, "yes": ship_yes, "of": len(votes), "votes": votes}
