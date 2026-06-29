"""Generic host-agent edit packets.

The current MCP host (Codex Desktop, Claude Code, or another capable assistant) can make editorial
decisions from transcript/QA context while Eddy keeps media handling, compile, render, QA, receipts,
and exact blockers in the engine.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eddy.config import load_config
from eddy.edit.compiler import CompileError, compile_edl
from eddy.edit.kernel import (
    EditCandidate,
    build_edit_candidates,
    candidates_by_id,
    opening_hook_cluster,
    raw_short_candidates,
)
from eddy.edit.retakes import filler_candidates, retake_candidates
from eddy.edit.simulate import simulate
from eddy.edit.schema import Cut, EditDecisions, EddyMeta, ProtectedMoment, Retake, ShortsCandidate, save
from eddy.host_loop import (
    append_history,
    elapsed_since_started,
    ensure_started,
    evaluate_repair_loop,
    qa_failure_signature,
    read_history,
)
from eddy.loop.receipts import Receipts
from eddy.media.probe import duration_s
from eddy.transcribe.pack import audio_silence_map, phrases as load_phrases, silence_map
from eddy.transcribe.whisper import words_flat

_MAX_PACKET_TEXT = 60_000


class HostRepairDirective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = ""
    action: str = ""
    reason: str = ""
    candidate_ids: list[str] = Field(default_factory=list)


class HostExpertOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    start_s: float
    end_s: float
    reason: str = ""
    quote: str = ""
    tier: Literal["MANDATORY", "RECOMMENDED", "OPTIONAL"] = "RECOMMENDED"
    expert_override: bool = False
    allow_expert_override: bool = False


class HostProtectedMoment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    start_s: float
    end_s: float
    reason: str = ""


class HostIntentV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: Literal["host_intent_v1"] = "host_intent_v1"
    edit_goal: str = ""
    keep_priorities: list[str] = Field(default_factory=list)
    drop_priorities: list[str] = Field(default_factory=list)
    retake_policy: str = "last_take_bias"
    gap_policy: str = "natural_micro_pauses"
    pacing_preference: str = "medium_clarity"
    shorts_preference: str = ""
    visual_insert_notes: list[dict[str, Any] | str] = Field(default_factory=list)
    targeted_repair_directives: list[HostRepairDirective] = Field(default_factory=list)
    selected_candidate_ids: list[str] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)
    candidate_annotations: dict[str, str] = Field(default_factory=dict)
    selected_opening_hook_variant_id: str = ""
    selected_short_candidate_ids: list[str] = Field(default_factory=list)
    shorts_candidates: list[ShortsCandidate] = Field(default_factory=list)
    retake_clean_policy: str = "last_clean_hook_wins"
    protected_moments: list[HostProtectedMoment] = Field(default_factory=list)
    raw_cuts: list[HostExpertOverride] = Field(default_factory=list)
    expert_overrides: list[HostExpertOverride] = Field(default_factory=list)
    target_runtime_seconds: float = 0
    edit_intensity: str = "medium_clarity"


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Path, limit: int = _MAX_PACKET_TEXT) -> str:
    if not path.exists():
        return ""
    return path.read_text(errors="replace")[:limit]


def _safe_words(run_dir: Path) -> list[dict]:
    try:
        return words_flat(run_dir)
    except Exception:
        return []


def _safe_json_list(loader, run_dir: Path) -> list[dict]:
    try:
        data = loader(run_dir)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _kernel_candidates(run_dir: Path) -> list[EditCandidate]:
    words = _safe_words(run_dir)
    if not words:
        return []
    return build_edit_candidates(
        words=words,
        transcript_gaps=_safe_json_list(silence_map, run_dir),
        audio_silence=_safe_json_list(audio_silence_map, run_dir),
        retakes=retake_candidates(words, limit=120),
        fillers=filler_candidates(words),
        max_candidates=240,
    )


def _host_payload_body(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("intent"), dict):
        return payload["intent"]
    if isinstance(payload.get("host_intent"), dict):
        return payload["host_intent"]
    return payload


def _is_host_intent_payload(payload: dict[str, Any]) -> bool:
    body = _host_payload_body(payload)
    return body.get("contract") == "host_intent_v1"


def _candidate_to_decision(candidate: EditCandidate, reason: str) -> Retake | Cut:
    if candidate.kind == "retake":
        return Retake(
            remove_start_s=candidate.start_s,
            remove_end_s=candidate.end_s,
            kept_take="last",
            quote=candidate.quote,
            reason=reason,
        )
    return Cut(
        start_s=candidate.start_s,
        end_s=candidate.end_s,
        quote=candidate.quote,
        reason=reason,
        tier="RECOMMENDED",
    )


def _intent_visual_notes(intent: HostIntentV1) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for item in intent.visual_insert_notes:
        if isinstance(item, str):
            if item.strip():
                notes.append({"note": item.strip(), "source": "host_intent_v1"})
        else:
            notes.append({**item, "source": item.get("source", "host_intent_v1")})
    return notes


def _opening_hook_cuts(intent: HostIntentV1, cluster: dict[str, Any] | None) -> list[Cut]:
    if not cluster or not cluster.get("variants"):
        return []
    variants = {variant["id"]: variant for variant in cluster.get("variants", [])}
    selected_id = intent.selected_opening_hook_variant_id or cluster.get("default_variant_id")
    selected = variants.get(selected_id)
    if not selected:
        raise ValueError(json.dumps({
            "code": "unknown_opening_hook_variant_id",
            "message": "The host selected an opening hook variant that is not in this packet.",
            "fix": "Call eddy_host_packet again and choose one opening_hook_context variant id.",
            "evidence": {"selected_opening_hook_variant_id": selected_id},
        }))
    if intent.retake_clean_policy.strip().lower() in {"off", "disabled", "none"}:
        return []

    cuts: list[Cut] = []
    cluster_start = float(cluster["start_s"])
    selected_start = float(selected["start_s"])
    if selected_start > cluster_start + 0.05:
        cuts.append(
            Cut(
                start_s=cluster_start,
                end_s=selected_start,
                quote=str(selected.get("text", ""))[:120],
                reason=(
                    "Opening Hook Cluster: keep selected hook variant and remove earlier hook "
                    "attempts according to last-clean-hook-wins."
                ),
                tier="MANDATORY",
            )
        )

    selected_end = float(selected["end_s"])
    for variant in cluster.get("variants", []):
        if variant["id"] == selected_id:
            continue
        start_s = float(variant["start_s"])
        end_s = float(variant["end_s"])
        if start_s > selected_end + 0.05:
            cuts.append(
                Cut(
                    start_s=start_s,
                    end_s=end_s,
                    quote=str(variant.get("text", ""))[:120],
                    reason="Opening Hook Cluster: remove unselected later hook attempt.",
                    tier="MANDATORY",
                )
            )
    return cuts


def _intent_short_candidates(
    intent: HostIntentV1,
    short_hints: list[dict[str, Any]] | None,
) -> list[ShortsCandidate]:
    indexed = {str(item.get("id")): item for item in short_hints or []}
    missing = [candidate_id for candidate_id in intent.selected_short_candidate_ids if candidate_id not in indexed]
    if missing:
        raise ValueError(json.dumps({
            "code": "unknown_short_candidate_ids",
            "message": "The host selected raw Shorts candidate IDs that are not in this packet.",
            "fix": "Call eddy_host_packet again and choose only IDs from shorts_candidate_context.candidates.",
            "evidence": {"unknown_ids": missing[:12]},
        }))
    out = list(intent.shorts_candidates)
    for candidate_id in dict.fromkeys(intent.selected_short_candidate_ids):
        item = indexed[candidate_id]
        out.append(
            ShortsCandidate(
                start_s=float(item["start_s"]),
                end_s=float(item["end_s"]),
                hook=str(item.get("hook", "")),
                reason=str(item.get("reason", "Host selected raw transcript Short candidate.")),
            )
        )
    return out


def _intent_to_decisions(
    intent: HostIntentV1,
    candidates: list[EditCandidate],
    *,
    opening_cluster: dict[str, Any] | None = None,
    short_hints: list[dict[str, Any]] | None = None,
) -> EditDecisions:
    indexed = candidates_by_id(candidates)
    missing = [candidate_id for candidate_id in intent.selected_candidate_ids if candidate_id not in indexed]
    if missing:
        raise ValueError(json.dumps({
            "code": "unknown_host_candidate_ids",
            "message": "The host selected candidate IDs that are not in this packet.",
            "fix": "Call eddy_host_packet again and select only IDs from candidate_context.candidates.",
            "evidence": {"unknown_ids": missing[:12]},
        }))

    retakes: list[Retake] = []
    cuts: list[Cut] = _opening_hook_cuts(intent, opening_cluster)
    for candidate_id in dict.fromkeys(intent.selected_candidate_ids):
        candidate = indexed[candidate_id]
        reason = intent.candidate_annotations.get(candidate_id) or candidate.reason
        decision = _candidate_to_decision(candidate, reason)
        if isinstance(decision, Retake):
            retakes.append(decision)
        else:
            cuts.append(decision)

    raw_overrides = [*intent.raw_cuts, *intent.expert_overrides]
    for override in raw_overrides:
        if not (override.expert_override or override.allow_expert_override):
            raise ValueError(json.dumps({
                "code": "raw_timestamp_override_requires_expert_override",
                "message": "Host intent used raw timestamps instead of Eddy candidate IDs.",
                "fix": "Select candidate IDs from eddy_host_packet, or mark the raw cut with expert_override=true.",
                "evidence": {"start_s": override.start_s, "end_s": override.end_s, "reason": override.reason},
            }))
        cuts.append(
            Cut(
                start_s=override.start_s,
                end_s=override.end_s,
                quote=override.quote,
                reason=f"Expert override: {override.reason}".strip(),
                tier=override.tier,
            )
        )

    shorts = _intent_short_candidates(intent, short_hints)
    directives = [
        {
            "contract": "host_intent_v1",
            "edit_goal": intent.edit_goal,
            "keep_priorities": intent.keep_priorities,
            "drop_priorities": intent.drop_priorities,
            "retake_policy": intent.retake_policy,
            "gap_policy": intent.gap_policy,
            "pacing_preference": intent.pacing_preference,
            "shorts_preference": intent.shorts_preference,
            "selected_candidate_ids": intent.selected_candidate_ids,
            "rejected_candidate_ids": intent.rejected_candidate_ids,
            "selected_opening_hook_variant_id": (
                intent.selected_opening_hook_variant_id
                or ((opening_cluster or {}).get("default_variant_id") if opening_cluster else "")
            ),
            "selected_short_candidate_ids": intent.selected_short_candidate_ids,
            "retake_clean_policy": intent.retake_clean_policy,
            "targeted_repair_directives": [directive.model_dump() for directive in intent.targeted_repair_directives],
        }
    ]
    return EditDecisions(
        target_runtime_seconds=intent.target_runtime_seconds,
        edit_intensity=intent.edit_intensity,
        retakes=retakes,
        cuts=cuts,
        protected_moments=[
            ProtectedMoment(start_s=span.start_s, end_s=span.end_s, reason=span.reason)
            for span in intent.protected_moments
        ],
        shorts_candidates=shorts,
        visual_insert_notes=_intent_visual_notes(intent),
        x_eddy=EddyMeta(directive=directives),
    )


def _latest_iteration(run_dir: Path) -> Path | None:
    iterations = sorted((run_dir / "iterations").glob("[0-9][0-9]"))
    return iterations[-1] if iterations else None


def _next_iteration(run_dir: Path) -> Path:
    iterations = sorted((run_dir / "iterations").glob("[0-9][0-9]"))
    next_n = (int(iterations[-1].name) + 1) if iterations else 1
    path = run_dir / "iterations" / f"{next_n:02d}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def host_packet(run_dir: Path | str) -> dict[str, Any]:
    """Build a bounded host-agent packet. It returns text/metadata only, never media bytes."""

    rd = Path(run_dir).expanduser()
    receipts = Receipts(rd)
    manifest = _read_json(rd / "manifest.json") or {}
    latest = _latest_iteration(rd)
    ensure_started(rd)
    candidates = _kernel_candidates(rd)
    words = _safe_words(rd)
    phrases = _safe_json_list(load_phrases, rd)
    hook_cluster = opening_hook_cluster(words, phrases)
    short_hints = raw_short_candidates(phrases, min_s=10.0, max_s=59.0) if phrases else []
    history = read_history(rd)
    loop_status = evaluate_repair_loop(history, elapsed_s=elapsed_since_started(rd))
    packet: dict[str, Any] = {
        "contract": "host_intent_v1",
        "status": "ready" if (rd / "transcript" / "takes_packed.md").exists() else "needs_transcript",
        "run_dir": str(rd),
        "instructions": (
            "Return host_intent_v1 JSON. Select Eddy candidate IDs and describe taste/repair intent; "
            "do not freehand raw timestamps unless you explicitly mark an expert override. Eddy will "
            "compile through the deterministic compiler, render locally, and pass/fail by Eddy QA gates."
        ),
        "schema": "host_intent_v1",
        "legacy_schema": "EditDecisions",
        "requested_host_action": {
            "type": "initial_intent" if not history else "repair_intent",
            "summary": (
                "Choose candidate IDs to remove, set keep/drop priorities, and add targeted repair "
                "directives for any current QA failures. If you do not choose an opening hook, Eddy "
                "defaults to the last clean opening hook variant."
            ),
            "required_payload_fields": [
                "contract",
                "edit_goal",
                "keep_priorities",
                "drop_priorities",
                "retake_policy",
                "gap_policy",
                "pacing_preference",
                "selected_candidate_ids",
                "targeted_repair_directives",
            ],
        },
        "media_policy": "No media bytes are included in this packet.",
        "source_hashes": manifest.get("source_sha256", {}),
        "sources": {
            key: {"path": str(path), "bytes_included": False}
            for key, path in (manifest.get("sources") or {}).items()
        },
        "transcript": {
            "path": str(rd / "transcript" / "takes_packed.md"),
            "excerpt": _read_text(rd / "transcript" / "takes_packed.md"),
        },
        "qa_context": {},
        "artifacts": {
            "words_json": str(rd / "transcript" / "words.json"),
            "phrases_json": str(rd / "transcript" / "phrases.json"),
        },
        "candidate_context": {
            "count": len(candidates),
            "candidates": [candidate.to_dict() for candidate in candidates],
            "selection_rule": (
                "Select candidate IDs. Eddy owns hard boundaries, word snapping, handles, protected "
                "content, compiler validation, and EDL generation."
            ),
        },
        "opening_hook_context": hook_cluster.to_dict() if hook_cluster else {
            "policy": "last_clean_hook_wins",
            "variants": [],
            "default_variant_id": "",
        },
        "shorts_candidate_context": {
            "count": len(short_hints),
            "candidates": short_hints,
            "selection_rule": "Select raw Shorts candidate IDs or submit explicit shorts_candidates.",
        },
        "repair_loop": {
            **loop_status,
            "budget": {"max_repair_passes": 10, "max_elapsed_s": 10800},
            "elapsed_s": round(elapsed_since_started(rd), 1),
            "history": history[-5:],
        },
    }
    if latest is not None:
        packet["qa_context"]["latest_iteration"] = latest.name
        for name in ("qa.json", "judge.json", "directive.json", "sim.json"):
            data = _read_json(latest / name)
            if data is not None:
                packet["qa_context"][name.removesuffix(".json")] = data
    final_qa = _read_json(rd / "final" / "qa-final.json")
    if final_qa is not None:
        packet["qa_context"]["final_qa"] = final_qa
    latest_sim = packet["qa_context"].get("sim") or packet["qa_context"].get("final_qa") or {}
    packet["retake_clean_context"] = {
        "failures": latest_sim.get("retake_clean", {}).get("failures", []) if isinstance(latest_sim, dict) else [],
        "policy": "Retake-clean edits cannot contain surviving false starts, hook retakes, or reset loops.",
    }
    receipts.log(
        "host_kernel_packet",
        status=packet["status"],
        contract=packet["contract"],
        transcript_chars=len(packet["transcript"]["excerpt"]),
        candidate_count=len(candidates),
        opening_hook_variants=len(hook_cluster.variants) if hook_cluster else 0,
        raw_short_candidates=len(short_hints),
        media_bytes_included=False,
        requested_host_action=packet["requested_host_action"]["type"],
    )
    if hook_cluster:
        receipts.log("opening_hook_cluster", **hook_cluster.to_dict())
    return packet


def _blocker_from_value_error(exc: ValueError) -> dict[str, Any]:
    try:
        data = json.loads(str(exc))
    except json.JSONDecodeError:
        data = {}
    if isinstance(data, dict) and data.get("code"):
        return data
    return {
        "code": "invalid_host_intent",
        "message": "The host intent payload could not be converted into Eddy decisions.",
        "fix": "Call eddy_host_packet again and submit host_intent_v1 JSON that selects candidate IDs.",
        "evidence": str(exc)[:500],
    }


def _payload_to_decisions(run_dir: Path, payload: dict[str, Any]) -> tuple[EditDecisions, str, HostIntentV1 | None]:
    if _is_host_intent_payload(payload):
        body = _host_payload_body(payload)
        intent = HostIntentV1.model_validate(body)
        words = _safe_words(run_dir)
        phrases = _safe_json_list(load_phrases, run_dir)
        cluster = opening_hook_cluster(words, phrases)
        hints = raw_short_candidates(phrases, min_s=10.0, max_s=59.0) if phrases else []
        return (
            _intent_to_decisions(
                intent,
                _kernel_candidates(run_dir),
                opening_cluster=cluster.to_dict() if cluster else None,
                short_hints=hints,
            ),
            "host_intent_v1",
            intent,
        )
    maybe_decisions = payload.get("decisions")
    legacy_body: Any = maybe_decisions if isinstance(maybe_decisions, dict) else payload
    return EditDecisions.model_validate(legacy_body), "EditDecisions", None


def _compile_host_decisions(
    rd: Path,
    decisions: EditDecisions,
    decisions_path: Path,
    receipts: Receipts,
    *,
    contract: str,
) -> dict[str, Any]:
    words_path = rd / "transcript" / "words.json"
    manifest_path = rd / "manifest.json"
    if not words_path.exists() or not manifest_path.exists():
        blocker: dict[str, Any] = {
            "code": "host_compile_context_missing",
            "message": "The host decisions were valid, but Eddy cannot compile them before transcription/source context exists.",
            "fix": "Run transcription first, then call eddy_host_packet and eddy_host_submit again.",
            "evidence": {"words_json": words_path.exists(), "manifest_json": manifest_path.exists()},
        }
        append_history(rd, {"status": "blocked", "contract": contract, "blocker": blocker})
        receipts.log("host_agent_submit_blocked", blocker=blocker, decisions_path=str(decisions_path), contract=contract)
        return {"status": "blocked", "blockers": [blocker], "decisions_path": str(decisions_path), "run_dir": str(rd)}

    manifest = json.loads(manifest_path.read_text())
    source_path = manifest.get("sources", {}).get("camera")
    if not source_path:
        blocker = {
            "code": "host_compile_source_missing",
            "message": "The run manifest does not identify a camera source for compilation.",
            "fix": "Open a normal Eddy run directory with a valid manifest, then retry.",
            "evidence": {"manifest": str(manifest_path)},
        }
        append_history(rd, {"status": "blocked", "contract": contract, "blocker": blocker})
        receipts.log("host_agent_submit_blocked", blocker=blocker, decisions_path=str(decisions_path), contract=contract)
        return {"status": "blocked", "blockers": [blocker], "decisions_path": str(decisions_path), "run_dir": str(rd)}

    cfg = load_config()
    phrases = load_phrases(rd)
    words = words_flat(rd)
    try:
        edl = compile_edl(
            decisions,
            words,
            str(source_path),
            duration_s(Path(source_path)),
            cfg.render,
            cfg.gates,
            silence_spans=audio_silence_map(rd),
            phrases=phrases,
            extract=decisions.x_eddy.focus_mode == "extract",
        )
    except CompileError as exc:
        blocker = {
            "code": "host_decisions_compile_failed",
            "message": "The host decisions were valid JSON but failed Eddy's deterministic compiler.",
            "fix": "Repair the listed intervals and submit a corrected host_intent_v1 or EditDecisions payload.",
            "evidence": exc.problems,
        }
        history = append_history(
            rd,
            {
                "status": "compile_failed",
                "contract": contract,
                "blocker": blocker,
                "failure_signature": json.dumps(exc.problems[:5], sort_keys=True),
            },
        )
        loop = evaluate_repair_loop(history, elapsed_s=elapsed_since_started(rd))
        receipts.log(
            "host_agent_submit_blocked",
            blocker=blocker,
            decisions_path=str(decisions_path),
            contract=contract,
            repair_loop=loop,
        )
        return {
            "status": "blocked",
            "blockers": [blocker],
            "decisions_path": str(decisions_path),
            "run_dir": str(rd),
            "repair_loop": loop,
        }

    manifest_sources = manifest.get("sources") or {}
    if manifest_sources:
        edl.sources = {str(key): str(value) for key, value in manifest_sources.items() if value}
        edl.sources["camera"] = str(source_path)

    sim_report = simulate(
        edl,
        decisions,
        phrases,
        cfg,
        decisions.target_runtime_seconds or edl.total_duration_s,
        words=words,
    )
    retake_failures = []
    if isinstance(sim_report, dict):
        retake_failures = (sim_report.get("retake_clean") or {}).get("failures", [])
    stamp = decisions_path.stem.rsplit("-", 1)[-1]
    host_dir = decisions_path.parent
    edl_path = host_dir / f"edl-{stamp}.json"
    save(edl, edl_path)
    iter_dir = _next_iteration(rd)
    save(decisions, iter_dir / "edit-decisions.json")
    save(edl, iter_dir / "edl.json")
    (iter_dir / "sim-report.json").write_text(json.dumps(sim_report, indent=1))
    history = append_history(
        rd,
        {
            "status": "compiled",
            "contract": contract,
            "iteration": iter_dir.name,
            "sim_pass": sim_report.get("pass"),
            "failure_signature": qa_failure_signature(sim_report if isinstance(sim_report, dict) else {}),
            "quality": float(sim_report.get("duration_score", 0.0) or 0.0) if isinstance(sim_report, dict) else 0.0,
        },
    )
    loop = evaluate_repair_loop(history, elapsed_s=elapsed_since_started(rd))
    receipts.log(
        "host_agent_submit",
        contract=contract,
        decisions_path=str(decisions_path),
        edl_path=str(edl_path),
        iteration_dir=str(iter_dir),
        ranges=len(edl.ranges),
        duration_s=edl.total_duration_s,
        sim_pass=sim_report.get("pass"),
        retake_clean_failures=len(retake_failures),
        repair_loop=loop,
    )
    return {
        "status": "compiled",
        "contract": contract,
        "run_dir": str(rd),
        "decisions_path": str(decisions_path),
        "edl_path": str(edl_path),
        "iteration_dir": str(iter_dir),
        "ranges": len(edl.ranges),
        "duration_s": edl.total_duration_s,
        "repair_loop": loop,
    }


def submit_host_decisions(run_dir: Path | str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and compile a host-agent payload.

    New hosts should submit host_intent_v1. Legacy hosts may still submit EditDecisions. Invalid host
    payloads are exact blockers. Valid payloads are written to disk and compiled through Eddy's normal
    compiler when transcript/source context is present.
    """

    rd = Path(run_dir).expanduser()
    receipts = Receipts(rd)
    ensure_started(rd)
    try:
        decisions, contract, intent = _payload_to_decisions(rd, payload)
    except ValidationError as exc:
        blocker: dict[str, Any] = {
            "code": "invalid_host_payload",
            "message": "The host assistant did not return a valid host_intent_v1 or EditDecisions payload.",
            "fix": "Submit host_intent_v1 JSON from eddy_host_packet, or legacy JSON that matches Eddy's EditDecisions schema.",
            "evidence": exc.errors(include_url=False)[:8],
        }
        receipts.log("host_agent_submit_blocked", blocker=blocker)
        return {"status": "blocked", "blockers": [blocker], "run_dir": str(rd)}
    except ValueError as exc:
        blocker = _blocker_from_value_error(exc)
        receipts.log("host_agent_submit_blocked", blocker=blocker)
        append_history(rd, {"status": "blocked", "contract": "host_intent_v1", "blocker": blocker})
        return {"status": "blocked", "blockers": [blocker], "run_dir": str(rd)}

    host_dir = rd / "host-agent"
    host_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    decisions_path = host_dir / f"edit-decisions-{stamp}.json"
    save(decisions, decisions_path)
    if intent is not None:
        intent_path = host_dir / f"host-intent-{stamp}.json"
        intent_path.write_text(json.dumps(intent.model_dump(), indent=1))
        receipts.log(
            "host_kernel_submit",
            intent_path=str(intent_path),
            selected_candidate_ids=intent.selected_candidate_ids,
            raw_override_count=len(intent.raw_cuts) + len(intent.expert_overrides),
        )

    return _compile_host_decisions(rd, decisions, decisions_path, receipts, contract=contract)
