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
from .plan import EditPlanV3, HookPlan, ShortPlan
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
) -> RenderPlan:
    work.mkdir(parents=True, exist_ok=True)
    sacred = [[float(item["start"]), float(item["end"])] for item in plan.protected]
    body_cutlist = work / "body-cutlist.json"
    body_dropfile = work / "body-drops.json"
    _write_json(
        body_cutlist,
        {
            "keep": [list(item) for item in plan.body.keep],
            "sacred": sacred,
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
        seen_spans.add(key)
        unique_rows.append(row)
    _write_json(body_dropfile, {"explicit_drops": unique_rows})
    renders: list[LongRenderPlan] = []
    for hook in plan.hooks:
        hook_path = work / f"hook-{hook.rank}-{_slug(hook.id)}-cutlist.json"
        _write_json(
            hook_path,
            {
                "keep": [list(item) for item in hook.segments],
                "sacred": sacred,
                "gap_tighten": {"threshold": 0.2, "target": 0.1},
            },
        )
        output_name = (
            "long-primary.mp4"
            if hook.rank == 1
            else f"long-alternate-{_slug(hook.id)}.mp4"
        )
        renders.append(LongRenderPlan(hook, hook_path, body_cutlist, output_name))
    return RenderPlan(body_cutlist, body_dropfile, tuple(renders))  # type: ignore[arg-type]


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
        render_plan = build_render_plan(plan, stage / "plans", ledger=ledger)
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

        def finish_attempt() -> None:
            _write_json(
                attempt / "qa.json",
                {
                    "longs": qa_rows,
                    "shorts": short_qa_rows,
                    "gates": gates,
                    "blockers": blockers,
                },
            )
            primary_words = stage / "final-words-1.json"
            _write_transcript_markdown(
                primary_words if primary_words.exists() else transcript,
                attempt / "transcript.md",
            )
            (attempt / "spot-check.md").write_text(
                "# Spot checks\n\nNo uncertain cuts were recorded by the host plan.\n"
            )
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
            long_segments = stage / f"camera-long-{item.hook.rank}.segments.json"
            _combine_segment_receipts(
                camera_hook.with_name(f"hook-camera-{item.hook.rank}.segments.json"),
                body_camera.with_name("body-camera.segments.json"),
                long_segments,
            )
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
            _concat(hook_composite, body_composite, composite)

            self.manager.transition(job_id, JobState.RENDERING_FINAL)
            motion_overlay = stage / f"motion-overlay-{item.hook.rank}.mp4"
            motioned = stage / f"motioned-{item.hook.rank}.mp4"
            long_beats = _motion_beats_for_hook(plan.motion_beats, item.hook.id)
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
            gates[f"contextual_motion_hook_{item.hook.rank}"] = context_green
            motion_green = (
                motion is not None
                and motion.returncode == 0
                and motioned.exists()
                and not fake_hyperframes
                and bool(motion_activity["pass"])
                and context_green
            )
            gates[f"hyperframes_motion_hook_{item.hook.rank}"] = motion_green
            if not motion_green:
                blockers.append(
                    "hyperframes_test_fixture_not_final"
                    if fake_hyperframes
                    else "hyperframes_motion_failed"
                )
            if not context_green:
                blockers.append("contextual_motion_fit_failed")

            self.manager.transition(job_id, JobState.ENHANCING_AUDIO)
            enhanced = long_dir / item.output_name
            audio_input = motioned if motion_green else composite
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
        gates["shared_body"] = body_camera.exists()
        if fatal_audio_failure:
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
                short_words = stage / f"short-{short_id}-words.json"
                _write_caption_words_for_segments(
                    transcript,
                    short_camera.with_name(f"short-{short_id}-camera.segments.json"),
                    short_words,
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
                        str(short_composite),
                        "--video-out",
                        str(captioned),
                        "--max-words",
                        "5",
                        "--proof-out",
                        str(short_punctuation_proof),
                    ],
                    cwd=self.root,
                )
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
                short_context_greens.append(short_context_green)
                short_motion_green = (
                    short_motion.returncode == 0
                    and short_motioned.exists()
                    and not fake_hyperframes
                    and bool(short_motion_activity["pass"])
                    and short_context_green
                )
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
                    proof = screen_proof_verdict(
                        short_final,
                        sources.screen,
                        short_camera.with_name(f"short-{short_id}-camera.segments.json"),
                        short.screen_proof_segments,
                        excluded_final_ranges=tuple(
                            (float(beat["start"]), float(beat["start"]) + float(beat["dur"]))
                            for beat in short.motion_beats
                        ),
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
) -> bool:
    repaired_any = False
    for pass_number in range(1, MAX_DELIVERED_CADENCE_PASSES + 1):
        violations = _delivered_gap_violations(final_words)
        if not violations:
            break
        duration = _media_duration(media)
        cutlist = work / f"{label}-delivered-cadence-{pass_number}-cutlist.json"
        repaired = work / f"{label}-delivered-cadence-{pass_number}.mp4"
        _write_json(
            cutlist,
            {
                "keep": [[0.0, duration]],
                "sacred": [],
                "gap_tighten": {"threshold": 0.2, "target": 0.1},
            },
        )
        before_sha256 = _sha256_file(media)
        _splice(root, media, final_words, cutlist, repaired)
        repair_segments = repaired.with_name(f"{repaired.stem}.segments.json")
        os.replace(repaired, media)
        _transcribe_final(root, media, final_words)
        after_violations = _delivered_gap_violations(final_words)
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
            if "descript_voice_consent_required" in error:
                return "descript_voice_consent_required"
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


def _write_caption_words_for_segments(
    transcript: Path,
    segment_receipt: Path,
    output: Path,
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
            mapped.append(
                {
                    "word": word.get("word", ""),
                    "start": round(output_cursor + clipped_start - segment_start, 3),
                    "end": round(output_cursor + clipped_end - segment_start, 3),
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
