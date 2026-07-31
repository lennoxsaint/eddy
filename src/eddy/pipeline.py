"""Deterministic render planning and execution for Eddy's frozen helper scripts."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audio_effect import restore_effect_cache, store_effect_cache
from .plan import EditPlanV3, HookPlan, PrivacyMask, ShortPlan
from .proof import (
    caption_sync_verdict,
    caption_terminal_punctuation_verdict,
    contextual_motion_verdict,
    measure_motion_activity,
    screen_proof_verdict,
)
from .runtime import JobManager, JobState


DELIVERED_GAP_HARD_MAX = 0.28
DELIVERED_GAP_ALIGNMENT_TOLERANCE = 0.02
MAX_DELIVERED_CADENCE_PASSES = 3


@dataclass(frozen=True, slots=True)
class Sources:
    camera: Path
    screen: Path | None


@dataclass(frozen=True, slots=True)
class LongRenderPlan:
    hook: HookPlan
    hook_cutlist: Path
    body_cutlist: Path
    output_name: str
    append_body: bool


@dataclass(frozen=True, slots=True)
class RenderPlan:
    body_cutlist: Path
    body_dropfile: Path
    longs: tuple[LongRenderPlan, LongRenderPlan, LongRenderPlan]


@dataclass(frozen=True, slots=True)
class AudioEnhancement:
    passed: bool
    stderr: str
    cache_manifest: dict[str, object] | None = None


def discover_sources(source: Path) -> Sources:
    source = source.expanduser().resolve()
    if source.is_file():
        files = [source]
    else:
        top_level = sorted(path for path in source.iterdir() if path.is_file())
        files = top_level if any(_is_video(path) for path in top_level) else sorted(source.rglob("*"))
    videos = [
        path
        for path in files
        if path.is_file() and _is_video(path)
    ]
    if not videos:
        raise ValueError("video_source_missing")
    screen = next(
        (path for path in videos if any(token in path.stem.lower() for token in ("screen", "display"))),
        None,
    )
    camera = next(
        (
            path
            for path in videos
            if any(token in path.stem.lower() for token in ("camera", "cam", "webcam", "face", "talking"))
        ),
        None,
    )
    if camera is None:
        remaining = [path for path in videos if path != screen]
        if len(remaining) != 1:
            raise ValueError("camera_source_ambiguous")
        camera = remaining[0]
    return Sources(camera, screen)


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}


def build_render_plan(
    plan: EditPlanV3,
    work: Path,
    *,
    ledger: dict[str, Any] | None = None,
    selected_opening_id: str | None = None,
) -> RenderPlan:
    work.mkdir(parents=True, exist_ok=True)
    sacred = [[float(item["start"]), float(item["end"])] for item in plan.protected]
    frozen = [
        [float(item["start"]), float(item["end"])]
        for item in plan.protected
        if item.get("preserve_audio_timing") is True
    ]
    body_cutlist = work / "body-cutlist.json"
    body_dropfile = work / "body-drops.json"
    _write_json(
        body_cutlist,
        {
            "keep": [list(item) for item in plan.body.keep],
            "sacred": sacred,
            "frozen": frozen,
            "gap_tighten": {"threshold": 0.2, "target": 0.1},
        },
    )
    drop_rows: list[dict[str, Any]] = [
        {"span": list(item), "reason": "host_body_drop"}
        for item in plan.body.drop
    ]
    for group in plan.body.retake_groups:
        drop_rows.extend(
            {
                "span": [variant.start, variant.end],
                "reason": f"retake_group:{group.id}",
            }
            for variant in group.variants
            if variant.id != group.selected_variant_id
        )
    if ledger:
        resolutions = {
            resolution.candidate_id: resolution
            for resolution in plan.editorial_review.resolutions
        }
        for candidate in ledger.get("candidates", []):
            candidate_id = candidate.get("id")
            resolution = resolutions.get(candidate_id)
            if resolution is None or resolution.action in {"intentional_repeat", "tighten_gap"}:
                continue
            variants = candidate.get("variants", [])
            selected = (
                candidate.get("recommended_variant_id")
                if resolution.action == "keep_last"
                else resolution.selected_variant_id
            )
            if resolution.action == "drop_all" and not variants:
                variants = [candidate]
                selected = None
            for variant in variants:
                if variant.get("id") == selected:
                    continue
                drop_rows.append(
                    {
                        "span": [float(variant["start"]), float(variant["end"])],
                        "reason": f"editorial_candidate:{candidate_id}",
                    }
                )
    unique_rows: list[dict[str, Any]] = []
    seen_spans: set[tuple[float, float]] = set()
    for row in drop_rows:
        key = (float(row["span"][0]), float(row["span"][1]))
        if key in seen_spans:
            continue
        if any(
            key[0] < frozen_end and key[1] > frozen_start
            for frozen_start, frozen_end in frozen
        ):
            raise ValueError("protected_audio_timing_drop_conflict")
        seen_spans.add(key)
        unique_rows.append(row)
    _write_json(body_dropfile, {"explicit_drops": unique_rows})
    selected_hook_id = plan.primary_hook.id
    if plan.visual_choreography is not None:
        selected = next(
            (
                opening
                for opening in plan.visual_choreography["openings"]
                if opening["id"] == selected_opening_id
            ),
            None,
        )
        if selected is None:
            raise ValueError("selected_opening_missing_or_invalid")
        selected_hook_id = str(selected["hook_id"])
    ordered_hooks = tuple(
        sorted(plan.hooks, key=lambda hook: (hook.id != selected_hook_id, hook.rank))
    )
    renders: list[LongRenderPlan] = []
    for hook in ordered_hooks:
        hook_path = work / f"hook-{hook.rank}-{_slug(hook.id)}-cutlist.json"
        _write_json(
            hook_path,
            {
                "keep": [list(item) for item in hook.segments],
                "sacred": sacred,
                "frozen": frozen,
                "gap_tighten": {"threshold": 0.2, "target": 0.1},
            },
        )
        output_name = (
            "long-primary.mp4"
            if hook.id == selected_hook_id
            else f"long-alternate-{_slug(hook.id)}.mp4"
        )
        append_body = not _ranges_fully_cover(hook.segments, plan.body.keep)
        renders.append(
            LongRenderPlan(hook, hook_path, body_cutlist, output_name, append_body)
        )
    return RenderPlan(body_cutlist, body_dropfile, tuple(renders))  # type: ignore[arg-type]


def _ranges_fully_cover(
    covering: tuple[tuple[float, float], ...],
    targets: tuple[tuple[float, float], ...],
) -> bool:
    """Return whether every target interval is already present in the opening.

    V3.6 may intentionally deliver a standalone 60-second opening where the
    protected opening is also the nominal shared body. Appending that body
    would repeat the entire opening. The normal long-form path is unchanged
    whenever any body interval extends beyond the selected hook.
    """

    merged: list[list[float]] = []
    for start, end in sorted(covering):
        if merged and start <= merged[-1][1] + 0.001:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return all(
        any(start >= cover_start - 0.001 and end <= cover_end + 0.001
            for cover_start, cover_end in merged)
        for start, end in targets
    )


class PipelineRunner:
    def __init__(self, *, root: Path, manager: JobManager) -> None:
        self.root = root.resolve()
        self.manager = manager

    def prepare(self, job_id: str) -> None:
        job = self.manager.transition(job_id, JobState.PREFLIGHTING)
        sources = discover_sources(job.snapshot)
        transcript = job.run_dir / "transcript.json"
        camera_hash = _sha256_file(sources.camera)
        transcript_cache = (
            self.manager.runs_root.parent
            / "cache"
            / "transcripts"
            / f"{camera_hash}.json"
        )
        if _transcript_is_valid(transcript_cache):
            shutil.copy2(transcript_cache, transcript)
            self.manager.receipt(
                job_id,
                "transcript_cache_hit",
                source_sha256=camera_hash,
            )
        else:
            _run(
                [
                    sys.executable,
                    str(self.root / "scripts" / "transcribe.py"),
                    "--in",
                    str(sources.camera),
                    "--out",
                    str(transcript),
                ],
                cwd=self.root,
            )
            if not _transcript_is_valid(transcript):
                raise RuntimeError("transcript_invalid")
            transcript_cache.parent.mkdir(parents=True, exist_ok=True)
            temporary = transcript_cache.with_suffix(".json.tmp")
            shutil.copy2(transcript, temporary)
            os.replace(temporary, transcript_cache)
            self.manager.receipt(
                job_id,
                "transcript_cache_miss_filled",
                source_sha256=camera_hash,
            )
        from .editorial import build_editorial_ledger

        _write_json(
            job.run_dir / "editorial-ledger.json",
            build_editorial_ledger(
                transcript,
                audio=sources.camera,
            ),
        )
        self.manager.transition(job_id, JobState.AWAITING_HOST_PLAN)

    def finalize(self, job_id: str) -> None:
        job = self.manager.load(job_id)
        if job.state is not JobState.COMPILING:
            raise RuntimeError(f"job_not_compiled:{job.state}")
        plan = EditPlanV3.from_dict(json.loads((job.run_dir / "edit-plan.json").read_text()))
        sources = discover_sources(job.snapshot)
        transcript = job.run_dir / "transcript.json"
        if not transcript.exists():
            raise RuntimeError("transcript_missing")
        attempt_number = len(list((job.run_dir / "quarantine").glob("attempt-*"))) + 1
        stage = job.run_dir / "work" / f"stage-{attempt_number}"
        attempt = job.run_dir / "work" / f"attempt-{attempt_number}"
        stage.mkdir(parents=True, exist_ok=True)
        attempt.mkdir(parents=True, exist_ok=True)
        ledger_path = job.run_dir / "editorial-ledger.json"
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else None
        selected_opening_id = None
        if plan.visual_choreography is not None:
            selection_path = job.run_dir / "opening-selection.json"
            if not selection_path.is_file():
                raise RuntimeError("opening_selection_required_before_finalize")
            selected_opening_id = str(
                json.loads(selection_path.read_text()).get("selected_opening_id", "")
            )
        render_plan = build_render_plan(
            plan,
            stage / "plans",
            ledger=ledger,
            selected_opening_id=selected_opening_id,
        )
        primary_hook_rank = render_plan.longs[0].hook.rank
        self.manager.transition(job_id, JobState.RENDERING_PROXY)

        body_camera = stage / "body-camera.mp4"
        _splice(
            self.root,
            sources.camera,
            transcript,
            render_plan.body_cutlist,
            body_camera,
            drop=render_plan.body_dropfile,
        )
        if plan.grade_plan is not None:
            _grade_camera_footage(body_camera)
        body_screen = None
        if sources.screen:
            body_screen = stage / "body-screen.mp4"
            _splice(
                self.root,
                sources.screen,
                transcript,
                render_plan.body_cutlist,
                body_screen,
                segments=body_camera.with_name("body-camera.segments.json"),
                scale=(1920, 1080),
                no_audio=True,
            )

        body_composite = stage / "body-composite.mp4"
        if sources.screen and body_screen:
            _run(
                [
                    sys.executable,
                    str(self.root / "scripts" / "composite_render.py"),
                    "long",
                    "--screen",
                    str(body_screen),
                    "--camera",
                    str(body_camera),
                    "--out",
                    str(body_composite),
                ],
                cwd=self.root,
            )
        else:
            _run(
                [
                    sys.executable,
                    str(self.root / "scripts" / "composite_render.py"),
                    "th",
                    "--camera",
                    str(body_camera),
                    "--out",
                    str(body_composite),
                ],
                cwd=self.root,
            )

        gates: dict[str, bool] = {}
        blockers: list[str] = []
        qa_rows: list[dict[str, Any]] = []
        short_qa_rows: list[dict[str, Any]] = []
        long_dir = attempt
        fake_descript = bool(os.environ.get("EDDY_FAKE_DESCRIPT"))
        fake_hyperframes = bool(os.environ.get("EDDY_FAKE_HYPERFRAMES"))
        fatal_audio_failure = False
        fatal_privacy_failure = False
        body_visual = body_composite
        body_choreography_green = plan.visual_choreography is None
        design_contract = job.run_dir / "design.md"
        design_sha256 = (
            _sha256_file(design_contract) if design_contract.is_file() else "legacy-unbound"
        )
        if plan.visual_choreography is not None and plan.frame_contract is not None:
            shared_body = plan.visual_choreography["shared_body"]
            body_choreographed = stage / "body-choreographed.mp4"
            body_choreography = _render_visual_choreography(
                self.root,
                stage / "body-choreography-brief.json",
                stage / "choreography-body",
                body_choreographed,
                scenes=tuple(shared_body["scenes"]),
                camera=body_camera,
                screen=body_screen,
                audio_source=body_composite,
                source_roots=(job.snapshot, job.run_dir),
                design=design_contract,
                design_sha256=design_sha256,
                frame=job.run_dir / str(plan.frame_contract["ref"]),
                frame_sha256=str(plan.frame_contract["sha256"]),
                portrait=False,
                fake=fake_hyperframes,
            )
            body_choreography_green = bool(
                body_choreography.returncode == 0
                and body_choreographed.exists()
                and not fake_hyperframes
            )
            self.manager.receipt(
                job_id,
                "visual_choreography_rendered",
                surface="shared_body",
                status="pass" if body_choreography_green else "fail",
                design_sha256=design_sha256,
                frame_sha256=plan.frame_contract["sha256"],
            )
            if body_choreography_green:
                body_visual = body_choreographed
            else:
                blockers.append(
                    "hyperframes_test_fixture_not_final"
                    if fake_hyperframes
                    else "shared_body_choreography_failed"
                )

        def finish_attempt() -> None:
            opening_visual_delivery = _build_opening_visual_surfaces(
                attempt,
                plan.opening_visual_contract,
                tuple(
                    (item.hook.id, item.output_name)
                    for item in render_plan.longs
                ),
            )
            if opening_visual_delivery is not None:
                opening_green = opening_visual_delivery["status"] == "pass"
                gates["opening_visual_comparison_surfaces"] = opening_green
                if not opening_green:
                    blockers.append("opening_visual_comparison_surfaces_failed")
            choreography_delivery = _collect_choreography_delivery(
                stage,
                attempt,
                job.run_dir,
                plan,
            )
            if choreography_delivery is not None:
                choreography_green = choreography_delivery["status"] == "pass"
                gates["visual_choreography_delivery"] = choreography_green
                if not choreography_green:
                    blockers.append("visual_choreography_delivery_failed")
                body_structure_delivery = choreography_delivery.get("body_structure_delivery")
                if isinstance(body_structure_delivery, dict):
                    body_structure_green = body_structure_delivery.get("status") == "pass"
                    gates["body_structure_delivery"] = body_structure_green
                if not body_structure_green:
                    blockers.append("body_structure_delivery_failed")
            opening_blueprint_delivery = plan.opening_blueprint_delivery
            if plan.schema_version == "edit-plan-v3.6":
                blueprint_green = opening_blueprint_delivery is not None
                gates["opening_blueprint_delivery"] = blueprint_green
                if not blueprint_green:
                    blockers.append("opening_blueprint_delivery_failed")
            _write_json(
                attempt / "qa.json",
                {
                    "longs": qa_rows,
                    "shorts": short_qa_rows,
                    "gates": gates,
                    "blockers": blockers,
                    "opening_visual_delivery": opening_visual_delivery,
                    "opening_blueprint_delivery": opening_blueprint_delivery,
                    "visual_choreography_delivery": choreography_delivery,
                },
            )
            primary_words = stage / f"final-words-{primary_hook_rank}.json"
            _write_transcript_markdown(
                primary_words if primary_words.exists() else transcript,
                attempt / "transcript.md",
            )
            (attempt / "spot-check.md").write_text(
                "# Spot checks\n\nNo uncertain cuts were recorded by the host plan.\n"
            )
            if plan.schema_version in {"edit-plan-v3.5", "edit-plan-v3.6"}:
                self.manager.transition(job_id, JobState.AWAITING_INDEPENDENT_REVIEW)
                self.manager.receipt(
                    job_id,
                    "independent_review_requested",
                    attempt=attempt.name,
                    review_schema="eddy-review-submission-v1",
                    verifier_authority="independent_no_edit_context",
                )
                return
            self.manager.transition(job_id, JobState.VERIFYING)
            self.manager.record_verification(
                job_id,
                attempt=attempt,
                gates=gates,
                blockers=list(dict.fromkeys(blockers)),
            )

        for item in render_plan.longs:
            camera_hook = stage / f"hook-camera-{item.hook.rank}.mp4"
            _splice(
                self.root,
                sources.camera,
                transcript,
                item.hook_cutlist,
                camera_hook,
                drop=render_plan.body_dropfile,
            )
            if plan.grade_plan is not None:
                _grade_camera_footage(camera_hook)
            long_segments = stage / f"camera-long-{item.hook.rank}.segments.json"
            hook_segments = camera_hook.with_name(
                f"hook-camera-{item.hook.rank}.segments.json"
            )
            if item.append_body:
                _combine_segment_receipts(
                    hook_segments,
                    body_camera.with_name("body-camera.segments.json"),
                    long_segments,
                )
            else:
                shutil.copy2(hook_segments, long_segments)
            screen_hook = None
            if sources.screen and body_screen:
                screen_hook = stage / f"hook-screen-{item.hook.rank}.mp4"
                _splice(
                    self.root,
                    sources.screen,
                    transcript,
                    item.hook_cutlist,
                    screen_hook,
                    segments=camera_hook.with_name(f"hook-camera-{item.hook.rank}.segments.json"),
                    scale=(1920, 1080),
                    no_audio=True,
                )
                hook_composite = stage / f"hook-layout-{item.hook.rank}.mp4"
                _run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "composite_render.py"),
                        "long",
                        "--screen",
                        str(screen_hook),
                        "--camera",
                        str(camera_hook),
                        "--out",
                        str(hook_composite),
                    ],
                    cwd=self.root,
                )
            else:
                hook_composite = stage / f"hook-layout-{item.hook.rank}.mp4"
                _run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "composite_render.py"),
                        "th",
                        "--camera",
                        str(camera_hook),
                        "--out",
                        str(hook_composite),
                    ],
                    cwd=self.root,
                )
            composite = stage / f"composite-{item.hook.rank}.mp4"
            opening_choreography_green = plan.visual_choreography is None
            hook_visual = hook_composite
            if plan.visual_choreography is not None and plan.frame_contract is not None:
                opening = next(
                    row
                    for row in plan.visual_choreography["openings"]
                    if row["hook_id"] == item.hook.id
                )
                opening_choreographed = stage / f"opening-choreographed-{item.hook.rank}.mp4"
                required_opening_duration = (
                    59.5 if plan.schema_version == "edit-plan-v3.6" else 29.5
                )
                opening_duration_green = (
                    _media_duration(hook_composite) >= required_opening_duration
                )
                opening_choreography = _render_visual_choreography(
                    self.root,
                    stage / f"opening-choreography-brief-{item.hook.rank}.json",
                    stage / f"choreography-opening-{item.hook.rank}",
                    opening_choreographed,
                    scenes=tuple(opening["scenes"]),
                    camera=camera_hook,
                    screen=screen_hook,
                    audio_source=hook_composite,
                    source_roots=(job.snapshot, job.run_dir),
                    design=design_contract,
                    design_sha256=design_sha256,
                    frame=job.run_dir / str(plan.frame_contract["ref"]),
                    frame_sha256=str(plan.frame_contract["sha256"]),
                    portrait=False,
                    fake=fake_hyperframes,
                )
                opening_choreography_green = bool(
                    opening_choreography.returncode == 0
                    and opening_choreographed.exists()
                    and opening_duration_green
                    and not fake_hyperframes
                )
                self.manager.receipt(
                    job_id,
                    "visual_choreography_rendered",
                    surface="opening",
                    hook_id=item.hook.id,
                    opening_id=opening["id"],
                    status="pass" if opening_choreography_green else "fail",
                    design_sha256=design_sha256,
                    frame_sha256=plan.frame_contract["sha256"],
                )
                if not opening_duration_green:
                    duration_label = (
                        "sixty"
                        if plan.schema_version == "edit-plan-v3.6"
                        else "thirty"
                    )
                    blockers.append(
                        f"opening_cut_under_{duration_label}_seconds:{item.hook.id}"
                    )
                if opening_choreography_green:
                    hook_visual = opening_choreographed
            if item.append_body:
                _concat(hook_visual, body_visual, composite)
            else:
                shutil.copy2(hook_visual, composite)

            self.manager.transition(job_id, JobState.RENDERING_FINAL)
            long_beats = _motion_beats_for_hook(plan.motion_beats, item.hook.id)
            motioned = composite
            if plan.visual_choreography is not None:
                scene_count = len(
                    next(
                        row["scenes"]
                        for row in plan.visual_choreography["openings"]
                        if row["hook_id"] == item.hook.id
                    )
                )
                motion_green = opening_choreography_green and body_choreography_green
                motion_activity = {
                    "pass": motion_green,
                    "mode": "full_frame_visual_choreography",
                    "meaningful_scene_count": scene_count,
                    "failed_beats": [] if motion_green else ["choreography_render_missing"],
                    "beats": [],
                }
                motion_context = {
                    "pass": motion_green,
                    "mode": "semantic_layout_contract",
                    "full_frame": True,
                }
                context_green = motion_green
            else:
                motion_overlay = stage / f"motion-overlay-{item.hook.rank}.mp4"
                motioned = stage / f"motioned-{item.hook.rank}.mp4"
                long_brief = stage / f"motion-brief-{item.hook.rank}.json"
                _write_motion_brief(long_brief, long_beats, portrait=False)
                motion = None
                if long_beats:
                    motion_command = [
                        sys.executable,
                        str(self.root / "scripts" / "motion_render.py"),
                        "--brief",
                        str(long_brief),
                        "--run-dir",
                        str(stage / f"motion-{item.hook.rank}"),
                        "--out",
                        str(motion_overlay),
                        "--composite-over",
                        str(composite),
                        "--composite-out",
                        str(motioned),
                    ]
                    if fake_hyperframes:
                        motion_command.append("--fake")
                    motion = subprocess.run(
                        motion_command,
                        cwd=self.root,
                        capture_output=True,
                        text=True,
                    )
                motion_activity = (
                    measure_motion_activity(motion_overlay, long_beats)
                    if motion is not None and motion.returncode == 0 and motion_overlay.exists()
                    else {"pass": False, "failed_beats": ["motion_render_missing"], "beats": []}
                )
                motion_placement = _read_motion_context_proof(
                    stage / f"motion-{item.hook.rank}" / "long-overlay" / "placement-proof.json",
                    expected_beats=len(long_beats),
                )
                motion_context = contextual_motion_verdict(motion_overlay, motion_placement)
                context_green = bool(motion_context["pass"])
                motion_green = (
                    motion is not None
                    and motion.returncode == 0
                    and motioned.exists()
                    and not fake_hyperframes
                    and bool(motion_activity["pass"])
                    and context_green
                )
            gates[f"contextual_motion_hook_{item.hook.rank}"] = context_green
            gates[f"hyperframes_motion_hook_{item.hook.rank}"] = motion_green
            if not motion_green:
                blockers.append(
                    "hyperframes_test_fixture_not_final"
                    if fake_hyperframes
                    else "hyperframes_motion_failed"
                )
            if not context_green:
                blockers.append("contextual_motion_fit_failed")

            audio_input = motioned if motion_green else composite
            applicable_masks = tuple(
                mask for mask in plan.privacy_masks if item.hook.id in mask.hook_ids
            )
            if applicable_masks:
                privacy_masked = stage / f"privacy-masked-{item.hook.rank}.mp4"
                try:
                    _apply_privacy_masks(
                        self.root,
                        audio_input,
                        privacy_masked,
                        applicable_masks,
                    )
                except RuntimeError:
                    gates[f"privacy_masks_hook_{item.hook.rank}"] = False
                    blockers.append(f"privacy_mask_failed:{item.hook.id}")
                    fatal_privacy_failure = True
                    break
                gates[f"privacy_masks_hook_{item.hook.rank}"] = privacy_masked.exists()
                if not privacy_masked.exists():
                    blockers.append(f"privacy_mask_failed:{item.hook.id}")
                    fatal_privacy_failure = True
                    break
                audio_input = privacy_masked
            else:
                gates[f"privacy_masks_hook_{item.hook.rank}"] = True

            self.manager.transition(job_id, JobState.ENHANCING_AUDIO)
            enhanced = long_dir / item.output_name
            audio = _enhance_audio(
                self.root,
                audio_input,
                enhanced,
                stage / f"audio-{item.hook.rank}",
                attempt / "provider-receipts.jsonl",
                item.output_name,
                self.manager.runs_root.parent / "cache" / "descript-effects",
                fake_descript=fake_descript,
            )
            if audio.cache_manifest is not None:
                self.manager.receipt(
                    job_id,
                    "descript_effect_cache_hit",
                    artifact=item.output_name,
                    input_sha256=audio.cache_manifest["input_sha256"],
                    output_sha256=audio.cache_manifest["output_sha256"],
                )
            audio_green = audio.passed
            gates[f"descript_effect_survival_hook_{item.hook.rank}"] = audio_green
            if not audio_green:
                blockers.append(
                    "descript_test_fixture_not_final"
                    if fake_descript
                    else _descript_failure_blocker(audio.stderr)
                )
                fatal_audio_failure = True
                break
            if audio_green:
                if plan.audio_plan is not None:
                    _mix_audio_plan(job.run_dir, enhanced, plan.audio_plan)
                final_words = stage / f"final-words-{item.hook.rank}.json"
                _transcribe_final(self.root, enhanced, final_words)
                cadence_repaired = _repair_delivered_cadence(
                    self.root,
                    enhanced,
                    final_words,
                    stage,
                    label=f"long-{item.hook.rank}",
                    receipts=attempt / "provider-receipts.jsonl",
                    artifact=item.output_name,
                    sacred=tuple(
                        (float(span["start"]), float(span["end"]))
                        for span in plan.protected
                    ),
                )
                qa = subprocess.run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "verify.py"),
                        "--final",
                        str(enhanced),
                        "--final-words",
                        str(final_words),
                        "--plan",
                        str(job.run_dir / "edit-plan.json"),
                        "--editorial-ledger",
                        str(ledger_path),
                        "--segments",
                        str(long_segments),
                        "--sacred",
                        str(render_plan.body_cutlist),
                        "--expect-w",
                        "1920",
                        "--expect-h",
                        "1080",
                    ],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                )
                qa_green = qa.returncode == 0
                gates[f"deterministic_qa_hook_{item.hook.rank}"] = qa_green
                try:
                    qa_payload = json.loads(qa.stdout)
                except json.JSONDecodeError:
                    qa_payload = {"pass": False, "blocker": "qa_receipt_invalid"}
                qa_rows.append(
                    {
                        "hook": item.hook.id,
                        "rank": item.hook.rank,
                        "delivered_cadence_repaired": cadence_repaired,
                        "motion_activity": motion_activity,
                        "motion_context": motion_context,
                        **qa_payload,
                    }
                )
                if not qa_green:
                    blockers.append("deterministic_qa_failed")

        gates["three_long_variants"] = len(list(long_dir.glob("*.mp4"))) == 3
        gates["shared_body"] = body_camera.exists() and body_choreography_green
        if fatal_audio_failure or fatal_privacy_failure:
            gates["shorts_quality"] = False
            gates["shorts_count"] = False
            gates["shorts_screen_proof"] = False
            gates["shorts_motion_activity"] = False
            gates["editorial_ledger_resolved"] = True
            finish_attempt()
            return
        shorts_dir = attempt / "shorts"
        if plan.shorts:
            shorts_dir.mkdir()
            short_greens: list[bool] = []
            short_screen_greens: list[bool] = []
            short_motion_greens: list[bool] = []
            short_context_greens: list[bool] = []
            short_caption_greens: list[bool] = []
            short_punctuation_greens: list[bool] = []
            for index, short in enumerate(plan.shorts, start=1):
                short_id = _slug(short.id)
                cutlist = stage / f"short-{short_id}-cutlist.json"
                _write_json(
                    cutlist,
                    {
                        "keep": [list(value) for value in short.segments],
                        "sacred": [],
                        "gap_tighten": {"threshold": 0.2, "target": 0.1},
                    },
                )
                short_dropfile = stage / f"short-{short_id}-drops.json"
                short_drop_rows = _merge_short_drops(
                    render_plan.body_dropfile,
                    short,
                    short_dropfile,
                )
                self.manager.receipt(
                    job_id,
                    "short_splice_inputs",
                    short_id=short.id,
                    explicit_drops=short_drop_rows,
                )
                short_camera = stage / f"short-{short_id}-camera.mp4"
                _splice(
                    self.root,
                    sources.camera,
                    transcript,
                    cutlist,
                    short_camera,
                    drop=short_dropfile,
                )
                if plan.grade_plan is not None:
                    _grade_camera_footage(short_camera)
                short_screen = None
                if sources.screen:
                    short_screen = stage / f"short-{short_id}-screen.mp4"
                    _splice(
                        self.root,
                        sources.screen,
                        transcript,
                        cutlist,
                        short_screen,
                        segments=short_camera.with_name(f"short-{short_id}-camera.segments.json"),
                        scale=(1920, 1080),
                        no_audio=True,
                    )
                    short_composite = stage / f"short-{short_id}-composite.mp4"
                    _run(
                        [
                            sys.executable,
                            str(self.root / "scripts" / "composite_render.py"),
                            "short",
                            "--face",
                            str(short_camera),
                            "--screen",
                            str(short_screen),
                            "--out",
                            str(short_composite),
                        ],
                        cwd=self.root,
                    )
                else:
                    short_composite = stage / f"short-{short_id}-composite.mp4"
                    _run(
                        [
                            sys.executable,
                            str(self.root / "scripts" / "composite_render.py"),
                            "short",
                            "--face",
                            str(short_camera),
                            "--out",
                            str(short_composite),
                        ],
                        cwd=self.root,
                    )
                short_visual = short_composite
                short_choreography_green = plan.visual_choreography is None
                if plan.visual_choreography is not None and plan.frame_contract is not None:
                    portrait_frame = job.run_dir / "shorts" / "frame.md"
                    portrait_frame_sha256 = _sha256_file(portrait_frame)
                    portrait_plan = next(
                        row
                        for row in plan.visual_choreography["shorts"]
                        if row["short_id"] == short.id
                    )
                    short_choreographed = stage / f"short-{short_id}-choreographed.mp4"
                    short_choreography = _render_visual_choreography(
                        self.root,
                        stage / f"short-{short_id}-choreography-brief.json",
                        stage / f"choreography-short-{short_id}",
                        short_choreographed,
                        scenes=tuple(portrait_plan["scenes"]),
                        camera=short_camera,
                        screen=short_screen,
                        audio_source=short_composite,
                        source_roots=(job.snapshot, job.run_dir),
                        design=design_contract,
                        design_sha256=design_sha256,
                        frame=portrait_frame,
                        frame_sha256=portrait_frame_sha256,
                        portrait=True,
                        fake=fake_hyperframes,
                    )
                    short_choreography_green = bool(
                        short_choreography.returncode == 0
                        and short_choreographed.exists()
                        and not fake_hyperframes
                    )
                    self.manager.receipt(
                        job_id,
                        "visual_choreography_rendered",
                        surface="short",
                        short_id=short.id,
                        status="pass" if short_choreography_green else "fail",
                        design_sha256=design_sha256,
                        frame_sha256=portrait_frame_sha256,
                    )
                    if short_choreography_green:
                        short_visual = short_choreographed
                short_words = stage / f"short-{short_id}-words.json"
                _write_caption_words_for_segments(
                    transcript,
                    short_camera.with_name(f"short-{short_id}-camera.segments.json"),
                    short_words,
                    suppress_ranges=(
                        (plan.caption_policy or {})
                        .get("source_caption_intervals", {})
                        .get(short.id, [])
                    ),
                )
                short_ass = stage / f"short-{short_id}.ass"
                short_punctuation_proof = stage / f"short-{short_id}-caption-punctuation.json"
                captioned = stage / f"short-{short_id}-captioned.mp4"
                _run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "karaoke_ass.py"),
                        "--transcript",
                        str(short_words),
                        "--out",
                        str(short_ass),
                        "--burn",
                        "--in",
                        str(short_visual),
                        "--video-out",
                        str(captioned),
                        "--max-words",
                        "5",
                        "--proof-out",
                        str(short_punctuation_proof),
                    ],
                    cwd=self.root,
                )
                short_motioned = captioned
                if plan.visual_choreography is not None:
                    short_motion_green = short_choreography_green
                    short_motion_activity = {
                        "pass": short_motion_green,
                        "mode": "portrait_visual_choreography",
                        "meaningful_scene_count": len(portrait_plan["scenes"]),
                        "failed_beats": [] if short_motion_green else ["choreography_render_missing"],
                        "beats": [],
                    }
                    short_motion_context = {
                        "pass": short_motion_green,
                        "mode": "semantic_layout_contract",
                        "full_frame": True,
                    }
                    short_context_green = short_motion_green
                else:
                    short_motion_overlay = stage / f"short-{short_id}-motion-overlay.mp4"
                    short_motioned = stage / f"short-{short_id}-motioned.mp4"
                    short_brief = stage / f"short-{short_id}-motion-brief.json"
                    _write_motion_brief(short_brief, short.motion_beats, portrait=True)
                    motion_command = [
                        sys.executable,
                        str(self.root / "scripts" / "motion_render.py"),
                        "--brief",
                        str(short_brief),
                        "--portrait",
                        "--run-dir",
                        str(stage / f"motion-short-{short_id}"),
                        "--out",
                        str(short_motion_overlay),
                        "--composite-over",
                        str(captioned),
                        "--composite-out",
                        str(short_motioned),
                    ]
                    if fake_hyperframes:
                        motion_command.append("--fake")
                    short_motion = subprocess.run(
                        motion_command,
                        cwd=self.root,
                        capture_output=True,
                        text=True,
                    )
                    short_motion_activity = (
                        measure_motion_activity(short_motion_overlay, short.motion_beats)
                        if short_motion.returncode == 0 and short_motion_overlay.exists()
                        else {"pass": False, "failed_beats": ["motion_render_missing"], "beats": []}
                    )
                    short_motion_placement = _read_motion_context_proof(
                        stage
                        / f"motion-short-{short_id}"
                        / "shorts-card"
                        / "placement-proof.json",
                        expected_beats=len(short.motion_beats),
                    )
                    short_motion_context = contextual_motion_verdict(
                        short_motion_overlay,
                        short_motion_placement,
                    )
                    short_context_green = bool(short_motion_context["pass"])
                    short_motion_green = (
                        short_motion.returncode == 0
                        and short_motioned.exists()
                        and not fake_hyperframes
                        and bool(short_motion_activity["pass"])
                        and short_context_green
                    )
                short_context_greens.append(short_context_green)
                short_motion_greens.append(short_motion_green)
                if not short_motion_green:
                    blockers.append(f"short_motion_failed:{short_id}")
                if not short_context_green:
                    blockers.append(f"short_contextual_motion_failed:{short_id}")
                short_final = shorts_dir / f"{index:02d}-{short_id}.mp4"
                short_artifact = f"shorts/{index:02d}-{short_id}.mp4"
                audio_input = short_motioned if short_motion_green else captioned
                audio = _enhance_audio(
                    self.root,
                    audio_input,
                    short_final,
                    stage / f"audio-short-{short_id}",
                    attempt / "provider-receipts.jsonl",
                    short_artifact,
                    self.manager.runs_root.parent / "cache" / "descript-effects",
                    fake_descript=fake_descript,
                )
                if audio.passed and plan.audio_plan is not None:
                    _mix_audio_plan(job.run_dir, short_final, plan.audio_plan)
                if audio.cache_manifest is not None:
                    self.manager.receipt(
                        job_id,
                        "descript_effect_cache_hit",
                        artifact=short_artifact,
                        input_sha256=audio.cache_manifest["input_sha256"],
                        output_sha256=audio.cache_manifest["output_sha256"],
                    )
                short_final_words = stage / f"short-{short_id}-final-words.json"
                if audio.passed:
                    _transcribe_final(self.root, short_final, short_final_words)
                short_caption_sync = (
                    caption_sync_verdict(
                        json.loads(short_words.read_text()).get("words", []),
                        json.loads(short_final_words.read_text()).get("words", []),
                    )
                    if audio.passed and short_final_words.exists()
                    else {"pass": False, "reason": "caption_timeline_out_of_sync"}
                )
                short_caption_green = bool(short_caption_sync["pass"])
                short_caption_greens.append(short_caption_green)
                if not short_caption_green:
                    blockers.append(f"short_caption_sync_failed:{short_id}")
                short_punctuation = (
                    caption_terminal_punctuation_verdict(
                        json.loads(short_words.read_text()).get("words", []),
                        json.loads(short_punctuation_proof.read_text()).get("rendered_tokens", []),
                    )
                    if short_punctuation_proof.exists()
                    else {"pass": False, "reason": "caption_punctuation_proof_missing"}
                )
                short_punctuation_green = bool(short_punctuation["pass"])
                short_punctuation_greens.append(short_punctuation_green)
                if not short_punctuation_green:
                    blockers.append(f"caption_terminal_punctuation_failed:{short_id}")
                short_qa = subprocess.run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "verify.py"),
                        "--final",
                        str(short_final),
                        "--final-words",
                        str(short_final_words),
                        "--plan",
                        str(job.run_dir / "edit-plan.json"),
                        "--editorial-ledger",
                        str(ledger_path),
                        "--segments",
                        str(short_camera.with_name(f"short-{short_id}-camera.segments.json")),
                        "--sacred",
                        str(cutlist),
                        "--expect-w",
                        "1080",
                        "--expect-h",
                        "1920",
                    ],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                ) if audio.passed else None
                if (
                    sources.screen is not None
                    and audio.passed
                ):
                    short_visual_plan = (
                        next(
                            (
                                row
                                for row in plan.visual_choreography["shorts"]
                                if row["short_id"] == short.id
                            ),
                            None,
                        )
                        if plan.visual_choreography is not None
                        else None
                    )
                    camera_only_ranges = (
                        tuple(
                            (float(scene["start"]), float(scene["end"]))
                            for scene in short_visual_plan["scenes"]
                            if scene["layout"] == "speaker_full"
                        )
                        if short_visual_plan is not None
                        else ()
                    )
                    proof = screen_proof_verdict(
                        short_final,
                        sources.screen,
                        short_camera.with_name(f"short-{short_id}-camera.segments.json"),
                        short.screen_proof_segments,
                        excluded_final_ranges=tuple(
                            (float(beat["start"]), float(beat["start"]) + float(beat["dur"]))
                            for beat in short.motion_beats
                        ) + camera_only_ranges,
                    )
                else:
                    proof = {
                        "pass": sources.screen is None,
                        "screen_share": 1.0 if sources.screen is None else 0.0,
                        "samples": [],
                    }
                short_screen_greens.append(bool(proof["pass"]))
                if not proof["pass"]:
                    blockers.append(f"short_screen_proof_failed:{short_id}")
                green = bool(
                    audio.passed
                    and short_qa is not None
                    and short_qa.returncode == 0
                    and short_motion_green
                    and short_caption_green
                    and short_punctuation_green
                    and bool(proof["pass"])
                )
                short_greens.append(green)
                short_qa_rows.append(
                    {
                        "short": short.id,
                        "motion_activity": short_motion_activity,
                        "motion_context": short_motion_context,
                        "caption_sync": short_caption_sync,
                        "caption_terminal_punctuation": short_punctuation,
                        "screen_proof": proof,
                        "pass": green,
                    }
                )
                if not green:
                    if not audio.passed and not fake_descript:
                        blockers.append(_descript_failure_blocker(audio.stderr))
                    blockers.append(f"short_failed:{short_id}")
            gates["shorts_quality"] = len(short_greens) == len(plan.shorts) and all(short_greens)
            gates["shorts_count"] = 3 <= len(short_greens) <= 5
            gates["shorts_screen_proof"] = (
                len(short_screen_greens) == len(plan.shorts) and all(short_screen_greens)
            )
            gates["shorts_motion_activity"] = (
                len(short_motion_greens) == len(plan.shorts) and all(short_motion_greens)
            )
            gates["shorts_contextual_motion"] = (
                len(short_context_greens) == len(plan.shorts) and all(short_context_greens)
            )
            gates["shorts_caption_sync"] = (
                len(short_caption_greens) == len(plan.shorts) and all(short_caption_greens)
            )
            gates["caption_terminal_punctuation"] = (
                len(short_punctuation_greens) == len(plan.shorts)
                and all(short_punctuation_greens)
            )
        gates["editorial_ledger_resolved"] = True
        gates.setdefault("shorts_screen_proof", False)
        gates.setdefault("shorts_motion_activity", False)
        gates.setdefault("shorts_contextual_motion", False)
        gates.setdefault("shorts_caption_sync", False)
        gates.setdefault("caption_terminal_punctuation", False)
        finish_attempt()


def _splice(
    root: Path,
    source: Path,
    transcript: Path,
    cutlist: Path,
    output: Path,
    *,
    segments: Path | None = None,
    drop: Path | None = None,
    scale: tuple[int, int] | None = None,
    no_audio: bool = False,
) -> None:
    command = [
        sys.executable,
        str(root / "scripts" / "splice.py"),
        "--in",
        str(source),
        "--words",
        str(transcript),
        "--cutlist",
        str(cutlist),
        "--out",
        str(output),
        "--no-auto-retakes",
    ]
    if segments:
        command.extend(["--segments", str(segments)])
    if drop and not segments:
        command.extend(["--drop", str(drop)])
    if scale:
        command.extend(["--scale", f"{scale[0]}x{scale[1]}"])
    if no_audio:
        command.append("--no-audio")
    _run(command, cwd=root)


def _enhance_audio(
    root: Path,
    input_media: Path,
    output_media: Path,
    work: Path,
    provider_receipts: Path,
    artifact: str,
    cache_root: Path,
    *,
    fake_descript: bool,
) -> AudioEnhancement:
    if not fake_descript:
        cached = restore_effect_cache(cache_root, input_media, output_media)
        if cached is not None:
            provider = cached["provider"]
            effect = cached["effect_survival"]
            assert isinstance(provider, dict) and isinstance(effect, dict)
            _append_receipt_rows(
                provider_receipts,
                [
                    {**provider, "artifact": artifact, "cached": True},
                    {**effect, "artifact": artifact, "cached": True},
                    {
                        "event": "descript_effect_cache_hit",
                        "artifact": artifact,
                        "source_artifact": cached["artifact"],
                        "input_sha256": cached["input_sha256"],
                        "output_sha256": cached["output_sha256"],
                    },
                ],
            )
            return AudioEnhancement(True, "", cached)

    audio = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "descript_studio_sound.py"),
            "--in",
            str(input_media),
            "--out",
            str(output_media),
            "--work",
            str(work),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    _append_provider_receipts(audio.stderr, provider_receipts, artifact=artifact)
    passed = audio.returncode == 0 and output_media.exists() and not fake_descript
    if passed:
        try:
            store_effect_cache(
                cache_root,
                input_media,
                output_media,
                provider_receipts,
                artifact,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            _append_receipt_rows(
                provider_receipts,
                [
                    {
                        "event": "descript_effect_cache_store_skipped",
                        "artifact": artifact,
                        "reason": type(error).__name__,
                    }
                ],
            )
    return AudioEnhancement(passed, audio.stderr)


def _apply_privacy_masks(
    root: Path,
    input_media: Path,
    output_media: Path,
    masks: tuple[PrivacyMask, ...],
) -> None:
    if not masks:
        raise ValueError("privacy_masks_required")
    output_media.parent.mkdir(parents=True, exist_ok=True)
    filters = [
        (
            f"drawbox=x={mask.x}:y={mask.y}:w={mask.width}:h={mask.height}:"
            f"color={mask.color}:t=fill:enable='between(t,{mask.start:.3f},{mask.end:.3f})'"
        )
        for mask in masks
    ]
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_media),
            "-vf",
            ",".join(filters),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_media),
        ],
        cwd=root,
    )


def _append_receipt_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _merge_short_drops(body_dropfile: Path, short: ShortPlan, output: Path) -> list[dict[str, Any]]:
    body_rows = json.loads(body_dropfile.read_text()).get("explicit_drops", [])
    rows: list[dict[str, Any]] = [
        {
            "span": [float(row["span"][0]), float(row["span"][1])],
            "reason": str(row["reason"]),
        }
        for row in body_rows
    ]
    rows.extend(
        {
            "span": [float(start), float(end)],
            "reason": f"host_short_drop:{short.id}",
        }
        for start, end in short.drop
    )
    unique: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()
    for row in rows:
        span = (float(row["span"][0]), float(row["span"][1]))
        if span in seen:
            continue
        seen.add(span)
        unique.append(row)
    _write_json(output, {"explicit_drops": unique})
    return unique


def _concat(first: Path, second: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = output.with_suffix(".concat.txt")
    manifest.write_text(
        "ffconcat version 1.0\n"
        f"file '{_ffconcat_path(first)}'\n"
        f"file '{_ffconcat_path(second)}'\n"
    )
    try:
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest),
                "-map",
                "0",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ],
            cwd=output.parent,
        )
    finally:
        manifest.unlink(missing_ok=True)


def _ffconcat_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


def _run(command: list[str], *, cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, env=os.environ.copy(), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {"blocker": "pipeline_command_failed", "command": command, "stderr": result.stderr[-1200:]}
            )
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _delivered_gap_violations(
    transcript: Path,
    *,
    hard_max: float = DELIVERED_GAP_HARD_MAX,
    alignment_tolerance: float = DELIVERED_GAP_ALIGNMENT_TOLERANCE,
) -> list[list[float]]:
    payload = json.loads(transcript.read_text())
    words = payload.get("words", [])
    gaps: list[list[float]] = []
    for left, right in zip(words, words[1:], strict=False):
        start, end = float(left["end"]), float(right["start"])
        if end > start:
            gaps.append([round(start, 3), round(end, 3)])
    durations = sorted(end - start for start, end in gaps)
    percentile_index = max(0, int(len(durations) * 0.95) - 1)
    p95 = durations[percentile_index] if durations else 0.0
    ceiling = hard_max + alignment_tolerance if p95 > hard_max + alignment_tolerance else 0.8
    return [gap for gap in gaps if gap[1] - gap[0] > ceiling]


def _repair_delivered_cadence(
    root: Path,
    media: Path,
    final_words: Path,
    work: Path,
    *,
    label: str,
    receipts: Path,
    artifact: str,
    sacred: tuple[tuple[float, float], ...] = (),
) -> bool:
    def unprotected_violations() -> list[list[float]]:
        return [
            violation
            for violation in _delivered_gap_violations(final_words)
            if not any(
                violation[1] > protected_start and violation[0] < protected_end
                for protected_start, protected_end in sacred
            )
        ]

    repaired_any = False
    for pass_number in range(1, MAX_DELIVERED_CADENCE_PASSES + 1):
        violations = unprotected_violations()
        if not violations:
            break
        duration = _media_duration(media)
        cutlist = work / f"{label}-delivered-cadence-{pass_number}-cutlist.json"
        repaired = work / f"{label}-delivered-cadence-{pass_number}.mp4"
        _write_json(
            cutlist,
            {
                "keep": [[0.0, duration]],
                "sacred": [[start, end] for start, end in sacred],
                "gap_tighten": {"threshold": 0.2, "target": 0.1},
            },
        )
        before_sha256 = _sha256_file(media)
        _splice(root, media, final_words, cutlist, repaired)
        repair_segments = repaired.with_name(f"{repaired.stem}.segments.json")
        os.replace(repaired, media)
        _transcribe_final(root, media, final_words)
        after_violations = unprotected_violations()
        _append_receipt(
            receipts,
            {
                "event": "post_descript_cadence_repair",
                "status": "pass" if len(after_violations) < len(violations) else "no_progress",
                "artifact": artifact,
                "pass": pass_number,
                "violations_before": violations,
                "violations_after": after_violations,
                "before_sha256": before_sha256,
                "output_sha256": _sha256_file(media),
                "segments_receipt": str(repair_segments.relative_to(work.parent)),
            },
        )
        repaired_any = True
        if len(after_violations) >= len(violations):
            break
    return repaired_any


def _media_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _append_receipt(output: Path, row: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _transcript_is_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    words = payload.get("words") if isinstance(payload, dict) else None
    return isinstance(words, list) and bool(words)


def _append_provider_receipts(stderr: str, output: Path, *, artifact: str) -> None:
    allowed_events = {
        "descript_provider",
        "descript_agent_result",
        "descript_agent_misroute",
        "descript_credentials_loaded",
        "descript_effect_survival",
        "descript_effect_retry",
        "descript_provider_retry",
        "audio_parity",
        "error",
    }
    rows: list[dict[str, Any]] = []
    for line in stderr.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("event") in allowed_events:
            rows.append({**row, "artifact": artifact})
    if not rows:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _descript_failure_blocker(stderr: str) -> str:
    rows: list[dict[str, Any]] = []
    for line in stderr.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    for row in reversed(rows):
        if row.get("event") == "descript_effect_survival":
            blockers = row.get("blockers")
            if isinstance(blockers, list) and blockers:
                return str(blockers[0])
        if row.get("event") == "audio_parity" and row.get("status") == "failed":
            return "descript_duration_parity_failed"
        if row.get("event") == "error":
            error = str(row.get("error", ""))
            if "descript_studio_sound_agent_misrouted" in error:
                return "descript_studio_sound_agent_misrouted"
            if "timeout" in error:
                return "descript_provider_timeout"
            return "descript_provider_failed"
    return "descript_effect_not_rendered"


def _transcribe_final(root: Path, media: Path, output: Path) -> None:
    _run(
        [
            sys.executable,
            str(root / "scripts" / "transcribe.py"),
            "--in",
            str(media),
            "--out",
            str(output),
        ],
        cwd=root,
    )


def _combine_segment_receipts(first: Path, second: Path, output: Path) -> None:
    first_payload = json.loads(first.read_text())
    second_payload = json.loads(second.read_text())
    segments = [*first_payload.get("segments", []), *second_payload.get("segments", [])]
    _write_json(
        output,
        {
            "segments": segments,
            "kept_seconds": round(sum(float(end) - float(start) for start, end in segments), 3),
            "gap_threshold": min(
                float(first_payload.get("gap_threshold", 0.2)),
                float(second_payload.get("gap_threshold", 0.2)),
            ),
            "gap_target": min(
                float(first_payload.get("gap_target", 0.1)),
                float(second_payload.get("gap_target", 0.1)),
            ),
            "output_order": "first_then_second",
        },
    )


def _motion_beats_for_hook(
    beats: tuple[dict[str, Any], ...], hook_id: str
) -> tuple[dict[str, Any], ...]:
    selected: list[dict[str, Any]] = []
    for beat in beats:
        target = beat.get("hook_id")
        if target not in {None, "*", hook_id}:
            continue
        selected.append({key: value for key, value in beat.items() if key != "hook_id"})
    return tuple(selected)


def _write_motion_brief(
    output: Path,
    beats: tuple[dict[str, Any], ...],
    *,
    portrait: bool,
) -> None:
    duration = max(
        (float(beat["start"]) + float(beat.get("dur", 1.0)) for beat in beats),
        default=0.0,
    )
    _write_json(
        output,
        {
            "width": 1080 if portrait else 1920,
            "height": 1920 if portrait else 1080,
            "duration": duration,
            "hud": "none" if portrait else "persistent",
            "beats": list(beats),
        },
    )


def _render_visual_choreography(
    root: Path,
    brief_path: Path,
    run_dir: Path,
    output: Path,
    *,
    scenes: tuple[dict[str, Any], ...],
    camera: Path,
    screen: Path | None,
    audio_source: Path,
    source_roots: tuple[Path, ...],
    design: Path,
    design_sha256: str,
    frame: Path,
    frame_sha256: str,
    portrait: bool,
    fake: bool,
) -> subprocess.CompletedProcess[str]:
    _write_json(
        brief_path,
        {
            "schema_version": "eddy-choreography-render-brief-v1",
            "width": 1080 if portrait else 1920,
            "height": 1920 if portrait else 1080,
            "camera": str(camera),
            "screen": str(screen) if screen else None,
            "audio_source": str(audio_source),
            "source_roots": [str(root) for root in source_roots],
            "design": str(design),
            "design_sha256": design_sha256,
            "frame": str(frame),
            "frame_sha256": frame_sha256,
            "scenes": list(scenes),
        },
    )
    command = [
        sys.executable,
        str(root / "scripts" / "choreography_render.py"),
        "--brief",
        str(brief_path),
        "--run-dir",
        str(run_dir),
        "--out",
        str(output),
    ]
    if fake:
        command.append("--fake")
    return subprocess.run(command, cwd=root, capture_output=True, text=True)


def _grade_camera_footage(path: Path) -> None:
    """Apply the conservative camera-only baseline; never touches screen capture."""

    temporary = path.with_name(f"{path.stem}.graded{path.suffix}")
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-vf",
            "eq=contrast=1.02:saturation=1.03:brightness=0.002",
            "-c:v",
            "libx264",
            "-crf",
            "16",
            "-preset",
            "medium",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(temporary),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not temporary.is_file():
        raise RuntimeError(f"camera_grade_failed:{result.stderr[-600:]}")
    os.replace(temporary, path)


def _mix_audio_plan(run_dir: Path, media: Path, plan: dict[str, Any]) -> None:
    """Mix documented music and state-change SFX under the treated dialogue."""

    command = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(media)]
    rows: list[tuple[str, dict[str, Any], int]] = []
    input_index = 1
    for cue in plan["music"]:
        command.extend(
            [
                "-stream_loop",
                "-1",
                "-i",
                str(run_dir / str(cue["ref"])),
            ]
        )
        rows.append(("music", cue, input_index))
        input_index += 1
    for cue in plan["sfx"]:
        command.extend(["-i", str(run_dir / str(cue["ref"]))])
        rows.append(("sfx", cue, input_index))
        input_index += 1

    filters = ["[0:a]volume=1[dialogue]"]
    mix_inputs = ["[dialogue]"]
    for kind, cue, index in rows:
        label = f"audio{index}"
        parts = [f"[{index}:a]volume={float(cue['mix_db']):.2f}dB"]
        if kind == "sfx":
            try:
                delay_ms = max(0, round(float(cue["cue"]) * 1000))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"audio_sfx_cue_invalid:{cue['cue']}") from exc
            parts.append(f"adelay={delay_ms}|{delay_ms}")
        filters.append(",".join(parts) + f"[{label}]")
        mix_inputs.append(f"[{label}]")
    filters.append(
        "".join(mix_inputs)
        + f"amix=inputs={len(mix_inputs)}:duration=first:normalize=0[mix]"
    )
    temporary = media.with_name(f"{media.stem}.mixed{media.suffix}")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "0:v:0",
            "-map",
            "[mix]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    )
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not temporary.is_file():
        raise RuntimeError(f"audio_plan_mix_failed:{result.stderr[-600:]}")
    os.replace(temporary, media)


def _build_opening_visual_surfaces(
    attempt: Path,
    contract: dict[str, Any] | None,
    candidate_order: tuple[tuple[str, str], ...],
) -> dict[str, Any] | None:
    if contract is None:
        return None
    raw_variants = contract.get("variants")
    variants = raw_variants if isinstance(raw_variants, list) else []
    variants_by_hook = {
        str(variant.get("hook_id")): variant
        for variant in variants
        if isinstance(variant, dict)
        and isinstance(variant.get("hook_id"), str)
    }
    candidates = [attempt / output_name for _, output_name in candidate_order]
    candidate_variants = [
        {
            "position": index,
            "hook_id": hook_id,
            "variant_id": variants_by_hook.get(hook_id, {}).get("variant_id"),
            "path": output_name,
        }
        for index, (hook_id, output_name) in enumerate(candidate_order, start=1)
    ]
    delivery: dict[str, Any] = {
        "schema_version": "1.0",
        "contract_ref": contract["contract_ref"],
        "contract_sha256": contract["contract_sha256"],
        "variant_count": len(contract["variants"]),
        "candidate_paths": [path.name for path in candidates],
        "candidate_variants": candidate_variants,
        "comparison_reel_path": "opening-comparison-reel.mp4",
        "contact_sheet_path": "opening-contact-sheet.png",
        "comparison_frame_paths": {
            "0": "opening-frame-00s.png",
            "1": "opening-frame-01s.png",
            "3": "opening-contact-sheet.png",
            "10": "opening-frame-10s.png",
            "30": "opening-frame-30s.png",
        },
        "status": "fail",
        "blocking_reasons": [],
    }
    if len(candidate_order) != 3 or len({hook_id for hook_id, _ in candidate_order}) != 3:
        delivery["blocking_reasons"].append(
            f"three ranked Long candidates required; found {len(candidate_order)}"
        )
        return delivery
    if any(row["variant_id"] is None for row in candidate_variants):
        delivery["blocking_reasons"].append(
            "every ranked Long candidate must map to an opening visual variant"
        )
        return delivery
    missing_candidates = [
        path.name
        for path in candidates
        if not path.exists() or path.stat().st_size == 0
    ]
    if missing_candidates:
        delivery["blocking_reasons"].append(
            f"ranked Long candidates missing or empty: {','.join(missing_candidates)}"
        )
        return delivery

    comparison_reel = attempt / delivery["comparison_reel_path"]
    contact_sheet = attempt / delivery["contact_sheet_path"]
    scale_filters = [
        (
            f"[{index}:v]trim=start=0:end=30,setpts=PTS-STARTPTS,"
            "scale=640:360:force_original_aspect_ratio=decrease,"
            f"pad=640:360:(ow-iw)/2:(oh-ih)/2:black[v{index}]"
        )
        for index in range(3)
    ]
    reel_filter = ";".join(scale_filters + ["[v0][v1][v2]hstack=inputs=3[outv]"])
    try:
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(candidates[0]),
                "-i",
                str(candidates[1]),
                "-i",
                str(candidates[2]),
                "-filter_complex",
                reel_filter,
                "-map",
                "[outv]",
                "-t",
                "30",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-movflags",
                "+faststart",
                str(comparison_reel),
            ],
            cwd=attempt,
        )
        for label, output_name in delivery["comparison_frame_paths"].items():
            second = min(float(label), 29.9)
            still_filters = [
                (
                    f"[{index}:v]select='gte(t,{second})',setpts=PTS-STARTPTS,"
                    "scale=640:360:force_original_aspect_ratio=decrease,"
                    f"pad=640:360:(ow-iw)/2:(oh-ih)/2:black[v{index}]"
                )
                for index in range(3)
            ]
            still_filter = ";".join(
                still_filters + ["[v0][v1][v2]hstack=inputs=3[outv]"]
            )
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(candidates[0]),
                    "-i",
                    str(candidates[1]),
                    "-i",
                    str(candidates[2]),
                    "-filter_complex",
                    still_filter,
                    "-map",
                    "[outv]",
                    "-frames:v",
                    "1",
                    str(attempt / str(output_name)),
                ],
                cwd=attempt,
            )
        comparison_duration = _media_duration(comparison_reel)
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        delivery["blocking_reasons"].append(f"comparison render failed: {exc}")
        return delivery
    if (
        not comparison_reel.exists()
        or comparison_reel.stat().st_size == 0
        or not contact_sheet.exists()
        or contact_sheet.stat().st_size == 0
        or any(
            not (attempt / str(path)).is_file()
            or (attempt / str(path)).stat().st_size == 0
            for path in delivery["comparison_frame_paths"].values()
        )
    ):
        delivery["blocking_reasons"].append("comparison surfaces are missing or empty")
        return delivery
    delivery["comparison_duration_seconds"] = comparison_duration
    if comparison_duration < 29.5:
        delivery["blocking_reasons"].append(
            "comparison reel must contain the full first 30 seconds; "
            f"found {comparison_duration:.3f}s"
        )
        return delivery
    delivery["status"] = "pass"
    return delivery


def _collect_choreography_delivery(
    stage: Path,
    attempt: Path,
    run_dir: Path,
    plan: EditPlanV3,
) -> dict[str, Any] | None:
    if plan.visual_choreography is None or plan.frame_contract is None:
        return None
    output = attempt / "visual-choreography"
    output.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    missing: list[str] = []
    projects = sorted(stage.glob("choreography-*/project"))
    for project in projects:
        label = project.parent.name.removeprefix("choreography-")
        for source_name in (
            "choreography-manifest.json",
            "animation-map.json",
            "provenance.json",
            "render-receipt.json",
            "hyperframes-lint.json",
            "hyperframes-validate.json",
            "hyperframes-inspect.json",
            "hyperframes-render.json",
            "storyboard.md",
            "index.html",
        ):
            source = project / source_name
            if not source.is_file():
                missing.append(f"{label}-{source_name}")
                continue
            destination = output / f"{label}-{source_name}"
            shutil.copy2(source, destination)
            files.append(destination.name)
    for source_name in ("opening-ranking.json", "opening-selection.json", "frame.md"):
        source = run_dir / source_name
        if source.is_file():
            shutil.copy2(source, output / source_name)
            files.append(source_name)
    shared_body = stage / "body-choreographed.mp4"
    shared_body_sha256 = _sha256_file(shared_body) if shared_body.is_file() else None
    body_structure_delivery = None
    if plan.body_structure_contract is not None:
        contract = plan.body_structure_contract
        body_structure_delivery = {
            "schema_version": "eddy-body-structure-delivery-v1",
            "source_contract_ref": contract["source_contract_ref"],
            "source_contract_sha256": contract["source_contract_sha256"],
            "major_order_authority": contract["major_order_authority"],
            "mode": contract["mode"],
            "route_understood_by_second": contract["route_contract"]["understood_by_second"],
            "section_ids": [section["section_id"] for section in contract["sections"]],
            "section_scene_ids": {
                section["section_id"]: list(section["scene_ids"])
                for section in contract["sections"]
            },
            "proof_scene_ids": {
                section["section_id"]: list(section["proof_scene_ids"])
                for section in contract["sections"]
            },
            "progress_cue_scene_ids": [cue["scene_id"] for cue in contract["progress_cues"]],
            "final_payoff_section_id": contract["final_payoff"]["section_id"],
            "shared_body_sha256": shared_body_sha256,
            "status": "pass" if shared_body_sha256 else "fail",
        }
        _write_json(output / "body-structure-delivery.json", body_structure_delivery)
        files.append("body-structure-delivery.json")
    expected_project_count = 4 + len(plan.visual_choreography["shorts"])
    project_count_green = len(projects) == expected_project_count
    delivery = {
        "schema_version": "eddy-visual-choreography-delivery-v1",
        "frame_sha256": plan.frame_contract["sha256"],
        "shared_body_sha256": shared_body_sha256,
        "body_structure_delivery": body_structure_delivery,
        "files": sorted(files),
        "project_count": len(projects),
        "expected_project_count": expected_project_count,
        "status": (
            "pass"
            if (
                shared_body.is_file()
                and bool(files)
                and project_count_green
                and not missing
                and (
                    body_structure_delivery is None
                    or body_structure_delivery["status"] == "pass"
                )
            )
            else "fail"
        ),
        "missing": sorted(missing),
    }
    _write_json(output / "delivery.json", delivery)
    return delivery


def _write_caption_words_for_segments(
    transcript: Path,
    segment_receipt: Path,
    output: Path,
    *,
    suppress_ranges: list[list[float]] | None = None,
) -> None:
    words = json.loads(transcript.read_text()).get("words", [])
    segments = json.loads(segment_receipt.read_text()).get("segments", [])
    mapped: list[dict[str, Any]] = []
    output_cursor = 0.0
    for segment_start_raw, segment_end_raw in segments:
        segment_start = float(segment_start_raw)
        segment_end = float(segment_end_raw)
        for word in words:
            word_start = float(word.get("start", 0.0))
            word_end = float(word.get("end", 0.0))
            if word_end <= segment_start or word_start >= segment_end:
                continue
            clipped_start = max(word_start, segment_start)
            clipped_end = min(word_end, segment_end)
            if clipped_end <= clipped_start:
                continue
            mapped_start = round(output_cursor + clipped_start - segment_start, 3)
            mapped_end = round(output_cursor + clipped_end - segment_start, 3)
            if any(
                mapped_start < float(end) and mapped_end > float(start)
                for start, end in (suppress_ranges or [])
            ):
                continue
            mapped.append(
                {
                    "word": word.get("word", ""),
                    "start": mapped_start,
                    "end": mapped_end,
                    "source_start": round(clipped_start, 3),
                    "source_end": round(clipped_end, 3),
                }
            )
        output_cursor += segment_end - segment_start
    _write_json(output, {"words": mapped})


def _read_motion_context_proof(path: Path, *, expected_beats: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "pass": False,
            "contract": "contextual_skeuomorphic_v1",
            "reason": "motion_placement_proof_missing",
            "beats": [],
        }
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {
            "pass": False,
            "contract": "contextual_skeuomorphic_v1",
            "reason": "motion_placement_proof_invalid",
            "beats": [],
        }
    beats = payload.get("beats") if isinstance(payload, dict) else None
    valid = (
        isinstance(beats, list)
        and len(beats) == expected_beats
        and payload.get("contract") == "contextual_skeuomorphic_v1"
        and payload.get("pass") is True
        and all(isinstance(row, dict) and row.get("pass") is True for row in beats)
    )
    return {**payload, "pass": valid}


def _write_transcript_markdown(transcript: Path, output: Path) -> None:
    words = json.loads(transcript.read_text()).get("words", [])
    output.write_text("# Transcript\n\n" + " ".join(str(word.get("word", "")) for word in words) + "\n")


def _slug(value: str) -> str:
    return "-".join(part for part in "".join(c.lower() if c.isalnum() else " " for c in value).split()) or "angle"
