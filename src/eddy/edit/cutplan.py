"""Model-driven editorial planning: beat map -> decisions -> (delta revisions)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from eddy.config import EddyConfig, load_config
from eddy.edit.compiler import CompileError, compile_edl
from eddy.edit.protect import enforce_protection_budget, setup_protections
from eddy.edit.schema import EditDecisions, EddyMeta, save
from eddy.loop.receipts import Receipts
from eddy.media.probe import duration_s as probe_duration
from eddy.providers.base import ProviderError, get_editorial_provider
from eddy.safety import detect_injection, fence
from eddy.runs import manifest
from eddy.transcribe.pack import audio_silence_map
from eddy.transcribe.pack import phrases as load_phrases
from eddy.transcribe.whisper import words_flat

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

BEATS_SCHEMA = {
    "type": "object",
    "required": ["beats"],
    "properties": {
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label", "start_s", "end_s"],
                "properties": {
                    "label": {"type": "string"},
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "summary": {"type": "string"},
                },
            },
        }
    },
}

DECISIONS_SCHEMA = {
    "type": "object",
    "required": ["retakes", "cuts", "protected_moments", "shorts_candidates"],
    "properties": {
        "target_runtime_seconds": {"type": "number"},
        "retakes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["remove_start_s", "remove_end_s"],
                "properties": {
                    "remove_start_s": {"type": "number"},
                    "remove_end_s": {"type": "number"},
                    "kept_take": {"type": "string", "enum": ["last", "earlier"]},
                    "quote": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "cuts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["start_s", "end_s", "tier"],
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "quote": {"type": "string"},
                    "reason": {"type": "string"},
                    "tier": {"type": "string", "enum": ["MANDATORY", "RECOMMENDED", "OPTIONAL"]},
                },
            },
        },
        "protected_moments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["start_s", "end_s"],
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "reason": {"type": "string"},
                },
            },
        },
        "cold_open": {
            "type": "object",
            "properties": {
                "start_s": {"type": "number"},
                "end_s": {"type": "number"},
                "reason": {"type": "string"},
            },
        },
        "shorts_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["start_s", "end_s"],
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "hook": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}


def packed_lines(phrases: list[dict]) -> str:
    return "\n".join(f"[{p['start']:.2f}-{p['end']:.2f}] {p['text']}" for p in phrases)


def _call(provider, receipts: Receipts, label: str, messages, schema, max_tokens=8192):
    t0 = time.time()
    try:
        result = provider.complete(messages, schema=schema, max_tokens=max_tokens)
        receipts.log("model_call", label=label, provider=provider.name, ok=True, wall_s=round(time.time() - t0, 1))
        return result
    except ProviderError as e:
        receipts.log("model_call", label=label, provider=provider.name, ok=False, error=str(e)[:300])
        raise


def beat_map(run_dir: Path, provider, receipts: Receipts) -> list[dict]:
    cache = Path(run_dir) / "transcript" / "beats.json"
    if cache.exists():
        return json.loads(cache.read_text())
    prompt = (PROMPTS / "beatmap.md").read_text()
    phrases = load_phrases(run_dir)
    packed = packed_lines(phrases)
    if flags := detect_injection(packed):
        receipts.log("prompt_injection_flagged", stage="beat_map", patterns=flags[:5])
    result = _call(
        provider,
        receipts,
        "beat_map",
        [{"role": "user", "content": f"{prompt}\n\n{fence('TRANSCRIPT', packed)}"}],
        BEATS_SCHEMA,
        max_tokens=2048,
    )
    cache.write_text(json.dumps(result["beats"], indent=1))
    return result["beats"]


def initial_decisions(
    run_dir: Path,
    provider,
    receipts: Receipts,
    target_s: float,
    retake_hints: list[dict],
    filler_hints: list[dict],
    beats: list[dict],
    cfg: EddyConfig,
) -> EditDecisions:
    from eddy.edit.simulate import raw_beat_density

    prompt = (PROMPTS / "cutplan.md").read_text()
    phrases = load_phrases(run_dir)
    # v0.3.2: hand the model the feasibility scale + density map UP FRONT, before it commits to
    # protections, so it cuts toward the ceiling instead of treating length as optional polish.
    # The loop's plateau used to quit ~20min over the ceiling because the model under-cut from
    # the first pass; this makes the size of the task explicit on iteration 1.
    ceiling_s = cfg.loop.length_ceiling_minutes * 60
    # use the same source duration the protection budget enforces against (probe of the camera
    # source), so the budget the model is TOLD matches the one compile_with_repair applies. Falls
    # back to the last spoken word if the manifest/source can't be probed.
    try:
        content_s = probe_duration(Path(manifest(run_dir)["sources"]["camera"]))
    except Exception:
        content_s = phrases[-1]["end"] if phrases else target_s
    remove_s = max(0.0, content_s - ceiling_s)
    pct = (remove_s / content_s * 100) if content_s > 0 else 0.0
    protect_budget_s = cfg.loop.protection_budget_frac * content_s
    length_budget = (
        f"LENGTH BUDGET (firm):\n"
        f"- Raw source is ~{content_s / 60:.0f} min ({content_s:.0f}s). HARD CEILING: "
        f"{cfg.loop.length_ceiling_minutes:.0f} min ({ceiling_s:.0f}s).\n"
        f"- To land under the ceiling you must remove roughly {remove_s:.0f}s "
        f"(~{pct:.0f}% of the runtime). Cutting is the primary lever — reaching the ceiling is "
        f"expected unless it would require cutting protected hook/payoff/CTA.\n"
        f"- Protect at most ~{protect_budget_s:.0f}s total "
        f"({cfg.loop.protection_budget_frac * 100:.0f}% of runtime); broad protections void your own cuts."
    )
    density = raw_beat_density(beats, phrases)
    density_lines = "\n".join(f"- {b['label']}: {b['span_s']:.0f}s @ {b['raw_wpm']:.0f}wpm" for b in density)
    content = (
        f"{prompt}\n\n"
        f"{length_budget}\n\n"
        f"BEAT DENSITY (raw, heaviest span first; long span + LOW wpm = draggy screen-reading, cut hardest):\n"
        f"{density_lines}\n\n"
        f"TARGET RUNTIME: {target_s:.0f} seconds\n\n"
        f"BEAT MAP:\n{json.dumps(beats, indent=1)}\n\n"
        f"RETAKE CANDIDATES (machine hints, adjudicate each):\n{json.dumps(retake_hints[:25], indent=1)}\n\n"
        f"FILLER/RESET MARKERS:\n{json.dumps(filler_hints[:15], indent=1)}\n\n"
        f"{fence('TRANSCRIPT', packed_lines(phrases))}"
    )
    if flags := detect_injection(packed_lines(phrases)):
        receipts.log("prompt_injection_flagged", stage="cutplan", patterns=flags[:5])
    raw = _call(provider, receipts, "cutplan", [{"role": "user", "content": content}], DECISIONS_SCHEMA)
    decisions = EditDecisions.model_validate({**raw, "target_runtime_seconds": target_s})
    decisions.x_eddy = EddyMeta(iteration=1, beats=beats)
    return decisions


def revise_decisions(
    run_dir: Path,
    provider,
    receipts: Receipts,
    previous: EditDecisions,
    directive: list[dict],
    iteration: int,
) -> EditDecisions:
    from eddy.edit.simulate import latest_post_cut_density

    prompt = (PROMPTS / "revise.md").read_text()
    phrases = load_phrases(run_dir)
    prev_json = json.dumps(previous.model_dump(exclude={"x_eddy"}), indent=1)
    # Close the pacing feedback loop: show the model the POST-CUT pacing its last edit produced
    # (was re-sending only the pre-cut raw density, so it never saw whether a draggy beat got tighter).
    density = latest_post_cut_density(run_dir)
    pacing_block = ""
    if density:
        lines = "\n".join(f"- {b['label']}: {b['kept_s']:.0f}s kept @ {b['wpm']:.0f}wpm" for b in density)
        pacing_block = (
            "PACING AFTER YOUR LAST EDIT (post-cut; a long kept span at LOW wpm is still draggy — "
            f"cut harder there):\n{lines}\n\n"
        )
    content = (
        f"{prompt}\n\n"
        f"YOUR PREVIOUS DECISIONS:\n{prev_json}\n\n"
        f"{pacing_block}"
        f"REVISION DIRECTIVE:\n{json.dumps(directive, indent=1)}\n\n"
        f"{fence('TRANSCRIPT', packed_lines(phrases))}"
    )
    raw = _call(provider, receipts, f"revise_iter{iteration}", [{"role": "user", "content": content}], DECISIONS_SCHEMA)
    decisions = EditDecisions.model_validate(
        {**raw, "target_runtime_seconds": previous.target_runtime_seconds}
    )
    parent_sha = hashlib.sha256(prev_json.encode()).hexdigest()[:12]
    decisions.x_eddy = EddyMeta(
        iteration=iteration, parent_sha=parent_sha, directive=directive, beats=previous.x_eddy.beats
    )
    return decisions


def compile_with_repair(
    run_dir: Path, decisions: EditDecisions, provider, receipts: Receipts, cfg: EddyConfig
):
    """Compile; on CompileError feed the structured problems back for delta repair (max 2)."""
    m = manifest(run_dir)
    words = words_flat(run_dir)
    src = m["sources"]["camera"]
    dur = probe_duration(Path(src))
    silence_spans = audio_silence_map(run_dir)
    # deterministic setup→payoff integrity: protect transition/setup lines so cuts can't
    # orphan the payoff they introduce
    extra_protected = setup_protections(load_phrases(run_dir))

    for attempt in range(3):
        # v0.3.2: enforce the protection budget the prompt asks for but never checked, on EVERY
        # (re)compile. Over-broad model protections void its own cuts (the compiler drops any cut
        # taking the majority of a protected span), so the edit can never reach the ceiling. This
        # must run inside the loop: revise_decisions (the repair path below) rebuilds
        # protected_moments from raw model output, so enforcing only once would let a repair restore
        # over-broad protections. Idempotent — a sub-budget set is returned untouched. The
        # deterministic setup_protections are added separately at compile and exempt from the budget.
        kept_prot, dropped_prot = enforce_protection_budget(
            list(decisions.protected_moments), dur, cfg.loop.protection_budget_frac
        )
        if dropped_prot:
            decisions.protected_moments = kept_prot
            receipts.log(
                "protection_budget", source_s=round(dur), budget_frac=cfg.loop.protection_budget_frac,
                kept=len(kept_prot), dropped=len(dropped_prot),
            )
        try:
            edl = compile_edl(
                decisions, words, src, dur, cfg.render, cfg.gates,
                silence_spans=silence_spans, extra_protected=extra_protected,
            )
            return decisions, edl
        except CompileError as e:
            receipts.log("compile_error", attempt=attempt, problems=e.problems[:10])
            if attempt == 2:
                raise
            directive = [{"op": "restore", "defect": p, "reason": "compiler rejected"} for p in e.problems[:10]]
            decisions = revise_decisions(
                run_dir, provider, receipts, decisions, directive, decisions.x_eddy.iteration
            )


def plan_run(run_dir: Path, target_minutes: float | None = None):
    """Standalone `eddy plan`: iteration-1 decisions + EDL + sim report."""
    from eddy.edit.retakes import filler_candidates, retake_candidates
    from eddy.edit.simulate import save_report, simulate

    run_dir = Path(run_dir).expanduser().resolve()
    cfg = load_config()
    receipts = Receipts(run_dir)
    provider = get_editorial_provider(cfg, receipts)
    target_s = (target_minutes or cfg.loop.default_target_minutes) * 60

    words = words_flat(run_dir)
    beats = beat_map(run_dir, provider, receipts)
    decisions = initial_decisions(
        run_dir, provider, receipts, target_s,
        retake_candidates(words), filler_candidates(words), beats, cfg,
    )
    decisions, edl = compile_with_repair(run_dir, decisions, provider, receipts, cfg)

    iter_dir = run_dir / "iterations" / "01"
    iter_dir.mkdir(parents=True, exist_ok=True)
    save(decisions, iter_dir / "edit-decisions.json")
    save(edl, iter_dir / "edl.json")
    report = simulate(edl, decisions, load_phrases(run_dir), cfg, target_s)
    save_report(report, iter_dir)
    receipts.log("plan", iteration=1, duration_s=edl.total_duration_s, sim_pass=report["pass"])
    print(json.dumps({k: report[k] for k in ("duration_s", "target_s", "ranges", "verdicts", "pass")}, indent=1))
    return iter_dir
