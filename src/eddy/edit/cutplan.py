"""Model-driven editorial planning: beat map -> decisions -> (delta revisions)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from eddy.config import EddyConfig, load_config
from eddy.edit.compiler import CompileError, compile_edl
from eddy.edit.schema import EditDecisions, EddyMeta, save
from eddy.loop.receipts import Receipts
from eddy.media.probe import duration_s as probe_duration
from eddy.providers.base import ProviderError, get_provider
from eddy.runs import manifest
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
    result = _call(
        provider,
        receipts,
        "beat_map",
        [{"role": "user", "content": f"{prompt}\n\nTRANSCRIPT:\n{packed_lines(phrases)}"}],
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
) -> EditDecisions:
    prompt = (PROMPTS / "cutplan.md").read_text()
    phrases = load_phrases(run_dir)
    content = (
        f"{prompt}\n\n"
        f"TARGET RUNTIME: {target_s:.0f} seconds\n\n"
        f"BEAT MAP:\n{json.dumps(beats, indent=1)}\n\n"
        f"RETAKE CANDIDATES (machine hints, adjudicate each):\n{json.dumps(retake_hints[:25], indent=1)}\n\n"
        f"FILLER/RESET MARKERS:\n{json.dumps(filler_hints[:15], indent=1)}\n\n"
        f"TRANSCRIPT:\n{packed_lines(phrases)}"
    )
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
    prompt = (PROMPTS / "revise.md").read_text()
    phrases = load_phrases(run_dir)
    prev_json = json.dumps(previous.model_dump(exclude={"x_eddy"}), indent=1)
    content = (
        f"{prompt}\n\n"
        f"YOUR PREVIOUS DECISIONS:\n{prev_json}\n\n"
        f"REVISION DIRECTIVE:\n{json.dumps(directive, indent=1)}\n\n"
        f"TRANSCRIPT:\n{packed_lines(phrases)}"
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

    for attempt in range(3):
        try:
            edl = compile_edl(decisions, words, src, dur, cfg.render, cfg.gates)
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
    provider = get_provider(cfg)
    target_s = (target_minutes or cfg.loop.default_target_minutes) * 60

    words = words_flat(run_dir)
    beats = beat_map(run_dir, provider, receipts)
    decisions = initial_decisions(
        run_dir, provider, receipts, target_s,
        retake_candidates(words), filler_candidates(words), beats,
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
