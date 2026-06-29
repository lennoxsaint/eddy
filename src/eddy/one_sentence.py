"""One-sentence Eddy orchestration: footage in, proof-gated edit or exact blockers out."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .atomicio import atomic_write_text
from .bootstrap import repair_plan
from .bundle import build_bundle
from .config import AUDIO_AUDITION_ENV, MOTION_MODE_ENV, load_config
from .doctor import detect, preflight
from .edit_options import edit_path_options, provider_for_edit_path
from .hooks.playbook import playbook_status, resolve_playbook_path
from .loop.receipts import Receipts
from .loop.controller import autonomous_run
from .formats import resolve_format
from .routing import choose_route
from .loop.state import RunState
from .runs import assert_sources_decodable, discover_sources, manifest as load_manifest, open_run, verify_sources_unmutated
from .templates import select_template, template_inventory


def _set_mode_env(motion_mode: str | None, audio_audition: str | None) -> dict[str, str | None]:
    previous = {MOTION_MODE_ENV: os.environ.get(MOTION_MODE_ENV), AUDIO_AUDITION_ENV: os.environ.get(AUDIO_AUDITION_ENV)}
    if motion_mode:
        os.environ[MOTION_MODE_ENV] = motion_mode.strip().lower()
    if audio_audition:
        os.environ[AUDIO_AUDITION_ENV] = audio_audition.strip().lower()
    return previous


def _restore_mode_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _motion_cache_ready(cache_dir: str) -> bool:
    cache = Path(cache_dir) / "hyperframes-pin.json"
    return cache.exists()


def _write_state(run_dir: Path, state: dict[str, Any]) -> None:
    atomic_write_text(run_dir / "one-sentence-state.json", json.dumps(state, indent=2, sort_keys=True) + "\n")


def _blocker(code: str, message: str, fix: str, evidence: Any | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "message": message, "fix": fix}
    if evidence is not None:
        item["evidence"] = evidence
    return item


def prepare_edit(
    source: Path | str,
    *,
    slug: str | None = None,
    focus: str | None = None,
    template_id: str | None = None,
    edit_path: str | None = None,
    auto_fallback: bool = True,
    fallback_policy: str = "agent_subscription",
    motion_mode: str | None = None,
    audio_audition: str | None = None,
    format_name: str = "youtube",
    repair: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Prepare a one-sentence edit and return ready/blocker state."""

    source_path = Path(source).expanduser()
    cfg = load_config()
    run_dir = open_run(source_path, slug=slug, focus=focus)
    manifest = load_manifest(run_dir)
    receipt_log = Receipts(run_dir)
    state = RunState(run_dir)
    state.set_phase("one_sentence_preflight")
    receipt_log.log(
        "one_sentence_started",
        source=str(source_path),
        dry_run=dry_run,
        repair=repair,
        edit_path=edit_path or "",
        auto_fallback=auto_fallback,
        fallback_policy=fallback_policy,
    )

    blockers: list[dict[str, Any]] = []
    checks = preflight()
    failed_checks = [check for check in checks if not check.get("ok", False)]
    if failed_checks:
        blockers.append(
            _blocker(
                "preflight_failed",
                "This machine is missing one or more capabilities Eddy needs before editing.",
                "Run `eddy doctor --no-write`, then follow the repair actions shown by `eddy bootstrap --dry-run`.",
                failed_checks,
            )
        )

    if repair:
        receipt_log.log("one_sentence_repair_requested", dry_run=dry_run)

    try:
        sources = discover_sources(source_path)
        assert_sources_decodable({key: str(path) for key, path in sources.items()})
    except Exception as exc:  # noqa: BLE001 - user-facing exact blocker
        blockers.append(
            _blocker(
                "source_discovery_failed",
                "Eddy could not discover or decode the raw footage cleanly.",
                "Check the file/folder path and provide non-corrupt camera/screen media.",
                str(exc),
            )
        )
        sources = {}

    try:
        template = select_template(sources, requested=template_id, focus=focus)
    except Exception as exc:  # noqa: BLE001 - user-facing exact blocker
        blockers.append(
            _blocker(
                "template_selection_failed",
                "Eddy could not match the footage to a safe edit template.",
                "Use a folder containing clearly named camera/screen files, or pass `--template`.",
                str(exc),
            )
        )
        template = None

    found = detect()
    route = choose_route(found)
    options = edit_path_options(
        found,
        source=source_path,
        format=format_name,
        focus=focus,
        selected=edit_path,
        auto_fallback=auto_fallback,
        fallback_policy=fallback_policy,
        cost_cap_usd=float(getattr(cfg.loop, "max_run_cost_usd", 0.0) or 0.0),
    )
    if options["status"] == "blocked":
        blockers.extend(options["blockers"])
    elif not route.can_execute and options.get("selected_option_id") != "host_kernel":
        blockers.append(
            _blocker(
                route.blockers[0] if route.blockers else "route_unavailable",
                route.reason,
                "Use Codex/Claude/API credentials, install a supported local model runtime, or configure an implemented Eddy cloud runner.",
                route.to_dict(),
            )
        )

    if template and "shorts" in template.outputs and cfg.shorts.require_hook_playbook:
        playbook = playbook_status(
            resolve_playbook_path(cfg.shorts.hook_playbook_path),
            min_records=cfg.shorts.hook_playbook_min_records,
        )
        if not playbook["ready"]:
            blockers.append(
                _blocker(
                    "hook_playbook_not_ready",
                    "Shorts generation is blocked because the baked hook playbook is not ready.",
                    "Run the hook-corpus build with Supadata inputs, commit the validated JSONL, then retry.",
                    playbook,
                )
            )

    if (
        template
        and "motion_graphics" in template.outputs
        and cfg.motion.mode.strip().lower() != "off"
        and not _motion_cache_ready(cfg.motion.cache_dir)
    ):
        blockers.append(
            _blocker(
                "hyperframes_cache_missing",
                "Motion graphics are blocked because the pinned HyperFrames cache is missing.",
                "Run `eddy motion update-hyperframes --hyperframes-root <path-to-hyperframes>` and retry.",
            )
        )

    status = "blocked" if blockers else "ready"
    state.set_phase(status)
    support_bundle = None
    summary: dict[str, Any] = {
        "status": status,
        "dry_run": dry_run,
        "run_dir": str(run_dir),
        "manifest": manifest,
        "sources": {key: str(path) for key, path in sources.items()},
        "template": template.to_dict() if template else None,
        "available_templates": template_inventory(),
        "route": route.to_dict(),
        "edit_options": options,
        "selected_edit_path": options.get("selected_option_id"),
        "auto_fallback": auto_fallback,
        "fallback_policy": fallback_policy,
        "preflight": checks,
        "repair_plan": repair_plan(checks),
        "blockers": blockers,
        "support_bundle": None,
        "next_action": (
            "Fix the blockers in order, then rerun `eddy edit <footage-folder>`."
            if blockers
            else "Run `eddy edit <footage-folder>` without --dry-run to render."
        ),
    }

    if blockers:
        _write_state(run_dir, summary)
        support_bundle = build_bundle(run_dir, run_dir / "support-bundle.zip")
        summary["support_bundle"] = str(support_bundle)
        _write_state(run_dir, summary)
        receipt_log.log("one_sentence_blocked", blockers=blockers, support_bundle=str(support_bundle))
    else:
        _write_state(run_dir, summary)
        receipt_log.log(
            "one_sentence_ready",
            template=template.id if template else None,
            route=route.tier,
            edit_path=options.get("selected_option_id"),
            fallback_order=options.get("fallback", {}).get("order", []),
        )

    verify_sources_unmutated(run_dir)
    return summary


def edit(
    source: Path | str,
    *,
    slug: str | None = None,
    focus: str | None = None,
    template_id: str | None = None,
    edit_path: str | None = None,
    auto_fallback: bool = True,
    fallback_policy: str = "agent_subscription",
    motion_mode: str | None = None,
    audio_audition: str | None = None,
    format_name: str = "youtube",
    language: str = "en",
    repair: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the one-sentence edit flow."""

    previous_modes = _set_mode_env(motion_mode, audio_audition)
    try:
        prepared = prepare_edit(
            source,
            slug=slug,
            focus=focus,
            template_id=template_id,
            edit_path=edit_path,
            auto_fallback=auto_fallback,
            fallback_policy=fallback_policy,
            motion_mode=motion_mode,
            audio_audition=audio_audition,
            format_name=format_name,
            repair=repair,
            dry_run=dry_run,
        )
        if prepared["status"] == "blocked" or dry_run:
            return prepared

        selected_edit_path = prepared.get("selected_edit_path")
        if selected_edit_path == "host_kernel":
            from .transcribe.whisper import transcribe_run
            from .host_agent import host_packet

            run_dir = Path(prepared["run_dir"])
            Receipts(run_dir).log(
                "host_kernel_route_started",
                edit_path="host_kernel",
                next_tool="eddy_host_packet",
                auto_fallback=auto_fallback,
                fallback_policy=fallback_policy,
            )
            transcribe_run(run_dir, language=language)
            packet = host_packet(run_dir)
            state = RunState(run_dir)
            state.set_phase("awaiting_host_intent")
            result = {
                **prepared,
                "status": "awaiting_host_intent",
                "legacy_status": "awaiting_host_decisions",
                "dry_run": False,
                "run_dir": str(run_dir),
                "host_contract": "host_intent_v1",
                "candidate_count": packet.get("candidate_context", {}).get("count", 0),
                "next_action": (
                    "Call eddy_host_packet(job_id), have the current assistant submit host_intent_v1 with "
                    "eddy_host_submit(job_id, payload), then render/QA through Eddy."
                ),
            }
            _write_state(run_dir, result)
            return result

        ceiling = resolve_format(format_name)["ceiling_minutes"]
        provider = provider_for_edit_path(selected_edit_path)
        previous = os.environ.get("EDDY_EDITORIAL")
        try:
            if provider:
                os.environ["EDDY_EDITORIAL"] = provider
            run_dir = autonomous_run(
                Path(source).expanduser(),
                slug=slug,
                skip_shorts=False,
                skip_package=False,
                language=language,
                ceiling_minutes=ceiling,
                focus=focus,
            )
        finally:
            if provider:
                if previous is None:
                    os.environ.pop("EDDY_EDITORIAL", None)
                else:
                    os.environ["EDDY_EDITORIAL"] = previous
    finally:
        _restore_mode_env(previous_modes)
    final_qa_path = run_dir / "final" / "qa-final.json"
    final_qa = json.loads(final_qa_path.read_text()) if final_qa_path.exists() else {"pass": False}
    status = "completed" if final_qa.get("pass") else "blocked"
    state = RunState(run_dir)
    state.set_phase(status)
    result = {
        **prepared,
        "status": status,
        "dry_run": False,
        "run_dir": str(run_dir),
        "final_qa": final_qa,
        "outputs": {
            "long_form": str(run_dir / "final" / "long" / "video.mp4"),
            "shorts_dir": str(run_dir / "final" / "shorts"),
            "package_dir": str(run_dir / "final" / "package"),
        },
        "next_action": (
            "Review the final outputs and promote/share only after human approval."
            if status == "completed"
            else "Open the support bundle and final QA report, repair the failing gate, then rerun."
        ),
    }
    if status != "completed":
        bundle = build_bundle(run_dir, run_dir / "support-bundle.zip")
        result["support_bundle"] = str(bundle)
        Receipts(run_dir).log("one_sentence_final_blocked", final_qa=final_qa, support_bundle=str(bundle))
    else:
        Receipts(run_dir).log("one_sentence_completed", final_qa=final_qa)
    _write_state(run_dir, result)
    return result
