"""Deterministic render planning and execution for Eddy's frozen helper scripts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .plan import EditPlanV3, HookPlan
from .runtime import JobManager, JobState


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
    longs: tuple[LongRenderPlan, LongRenderPlan, LongRenderPlan]


def discover_sources(source: Path) -> Sources:
    source = source.expanduser().resolve()
    files = [source] if source.is_file() else sorted(source.rglob("*"))
    videos = [
        path
        for path in files
        if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
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


def build_render_plan(plan: EditPlanV3, work: Path) -> RenderPlan:
    work.mkdir(parents=True, exist_ok=True)
    sacred = [[float(item["start"]), float(item["end"])] for item in plan.protected]
    body_cutlist = work / "body-cutlist.json"
    _write_json(
        body_cutlist,
        {
            "keep": [list(item) for item in plan.body.keep],
            "sacred": sacred,
            "gap_tighten": {"threshold": 0.2, "target": 0.1},
        },
    )
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
    return RenderPlan(body_cutlist, tuple(renders))  # type: ignore[arg-type]


class PipelineRunner:
    def __init__(self, *, root: Path, manager: JobManager) -> None:
        self.root = root.resolve()
        self.manager = manager

    def prepare(self, job_id: str) -> None:
        job = self.manager.transition(job_id, JobState.PREFLIGHTING)
        sources = discover_sources(job.source)
        _run(
            [
                sys.executable,
                str(self.root / "scripts" / "transcribe.py"),
                "--in",
                str(sources.camera),
                "--out",
                str(job.run_dir / "transcript.json"),
            ],
            cwd=self.root,
        )
        self.manager.transition(job_id, JobState.AWAITING_HOST_PLAN)

    def finalize(self, job_id: str) -> None:
        job = self.manager.load(job_id)
        if job.state is not JobState.COMPILING:
            raise RuntimeError(f"job_not_compiled:{job.state}")
        plan = EditPlanV3.from_dict(json.loads((job.run_dir / "edit-plan.json").read_text()))
        sources = discover_sources(job.source)
        transcript = job.run_dir / "transcript.json"
        if not transcript.exists():
            raise RuntimeError("transcript_missing")
        stage = job.run_dir / "work" / "stage-1"
        attempt = job.run_dir / "work" / "attempt-1"
        stage.mkdir(parents=True, exist_ok=True)
        attempt.mkdir(parents=True, exist_ok=True)
        render_plan = build_render_plan(plan, stage / "plans")
        self.manager.transition(job_id, JobState.RENDERING_PROXY)

        body_camera = stage / "body-camera.mp4"
        _splice(self.root, sources.camera, transcript, render_plan.body_cutlist, body_camera)
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
                no_audio=True,
            )

        gates: dict[str, bool] = {}
        blockers: list[str] = []
        qa_rows: list[dict[str, Any]] = []
        long_dir = attempt
        fake_descript = bool(os.environ.get("EDDY_FAKE_DESCRIPT"))
        fake_hyperframes = bool(os.environ.get("EDDY_FAKE_HYPERFRAMES"))
        for item in render_plan.longs:
            camera_hook = stage / f"hook-camera-{item.hook.rank}.mp4"
            _splice(self.root, sources.camera, transcript, item.hook_cutlist, camera_hook)
            camera_long = stage / f"camera-long-{item.hook.rank}.mp4"
            _concat(camera_hook, body_camera, camera_long)
            if sources.screen and body_screen:
                screen_hook = stage / f"hook-screen-{item.hook.rank}.mp4"
                _splice(
                    self.root,
                    sources.screen,
                    transcript,
                    item.hook_cutlist,
                    screen_hook,
                    segments=camera_hook.with_name(f"hook-camera-{item.hook.rank}.segments.json"),
                    no_audio=True,
                )
                screen_long = stage / f"screen-long-{item.hook.rank}.mp4"
                _concat(screen_hook, body_screen, screen_long)
                composite = stage / f"composite-{item.hook.rank}.mp4"
                _run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "composite_render.py"),
                        "long",
                        "--screen",
                        str(screen_long),
                        "--camera",
                        str(camera_long),
                        "--out",
                        str(composite),
                    ],
                    cwd=self.root,
                )
            else:
                composite = stage / f"composite-{item.hook.rank}.mp4"
                _run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "composite_render.py"),
                        "th",
                        "--camera",
                        str(camera_long),
                        "--out",
                        str(composite),
                    ],
                    cwd=self.root,
                )

            self.manager.transition(job_id, JobState.RENDERING_FINAL)
            motion_overlay = stage / f"motion-overlay-{item.hook.rank}.mp4"
            motioned = stage / f"motioned-{item.hook.rank}.mp4"
            motion_command = [
                sys.executable,
                str(self.root / "scripts" / "motion_render.py"),
                "--hook",
                item.hook.id,
                "--run-dir",
                str(stage / f"motion-{item.hook.rank}"),
                "--out",
                str(motion_overlay),
                "--duration",
                "2",
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
            motion_green = motion.returncode == 0 and motioned.exists() and not fake_hyperframes
            gates[f"hyperframes_motion_hook_{item.hook.rank}"] = motion_green
            if not motion_green:
                blockers.append(
                    "hyperframes_test_fixture_not_final"
                    if fake_hyperframes
                    else "hyperframes_motion_failed"
                )

            self.manager.transition(job_id, JobState.ENHANCING_AUDIO)
            enhanced = long_dir / item.output_name
            audio = subprocess.run(
                [
                    sys.executable,
                    str(self.root / "scripts" / "descript_studio_sound.py"),
                    "--in",
                    str(motioned if motion_green else composite),
                    "--out",
                    str(enhanced),
                    "--work",
                    str(stage / f"audio-{item.hook.rank}"),
                ],
                cwd=self.root,
                capture_output=True,
                text=True,
            )
            audio_green = audio.returncode == 0 and enhanced.exists() and not fake_descript
            gates[f"descript_effect_survival_hook_{item.hook.rank}"] = audio_green
            if not audio_green:
                blockers.append(
                    "descript_test_fixture_not_final"
                    if fake_descript
                    else "descript_effect_not_rendered"
                )
            if audio_green:
                final_words = stage / f"final-words-{item.hook.rank}.json"
                _write_final_words(transcript, item.hook, plan, final_words)
                qa = subprocess.run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "verify.py"),
                        "--final",
                        str(enhanced),
                        "--final-words",
                        str(final_words),
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
                qa_rows.append({"hook": item.hook.id, "rank": item.hook.rank, **qa_payload})
                if not qa_green:
                    blockers.append("deterministic_qa_failed")

        gates["three_long_variants"] = len(list(long_dir.glob("*.mp4"))) == 3
        gates["shared_body"] = body_camera.exists()
        shorts_dir = attempt / "shorts"
        if plan.shorts:
            shorts_dir.mkdir()
            short_greens: list[bool] = []
            for index, short in enumerate(plan.shorts, start=1):
                short_id = _slug(str(short["id"]))
                cutlist = stage / f"short-{short_id}-cutlist.json"
                _write_json(
                    cutlist,
                    {
                        "keep": short["segments"],
                        "sacred": [],
                        "gap_tighten": {"threshold": 0.2, "target": 0.1},
                    },
                )
                short_camera = stage / f"short-{short_id}-camera.mp4"
                _splice(self.root, sources.camera, transcript, cutlist, short_camera)
                if sources.screen:
                    short_screen = stage / f"short-{short_id}-screen.mp4"
                    _splice(
                        self.root,
                        sources.screen,
                        transcript,
                        cutlist,
                        short_screen,
                        segments=short_camera.with_name(f"short-{short_id}-camera.segments.json"),
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
                _write_words_for_ranges(transcript, short["segments"], short_words)
                short_ass = stage / f"short-{short_id}.ass"
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
                    ],
                    cwd=self.root,
                )
                short_final = shorts_dir / f"{index:02d}-{short_id}.mp4"
                audio = subprocess.run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "descript_studio_sound.py"),
                        "--in",
                        str(captioned),
                        "--out",
                        str(short_final),
                        "--work",
                        str(stage / f"audio-short-{short_id}"),
                    ],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                )
                short_qa = subprocess.run(
                    [
                        sys.executable,
                        str(self.root / "scripts" / "verify.py"),
                        "--final",
                        str(short_final),
                        "--final-words",
                        str(short_words),
                        "--expect-w",
                        "1080",
                        "--expect-h",
                        "1920",
                    ],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                ) if audio.returncode == 0 else None
                green = (
                    audio.returncode == 0
                    and not fake_descript
                    and short_qa is not None
                    and short_qa.returncode == 0
                )
                short_greens.append(green)
                if not green:
                    blockers.append(f"short_failed:{short_id}")
            gates["shorts_quality"] = len(short_greens) == len(plan.shorts) and all(short_greens)
            gates["shorts_count"] = 3 <= len(short_greens) <= 5
        _write_json(attempt / "qa.json", {"longs": qa_rows, "gates": gates, "blockers": blockers})
        _write_transcript_markdown(transcript, attempt / "transcript.md")
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


def _splice(
    root: Path,
    source: Path,
    transcript: Path,
    cutlist: Path,
    output: Path,
    *,
    segments: Path | None = None,
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
    ]
    if segments:
        command.extend(["--segments", str(segments)])
    if no_audio:
        command.append("--no-audio")
    _run(command, cwd=root)


def _concat(first: Path, second: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if _has_audio(first) and _has_audio(second):
        command = [
            "ffmpeg", "-y", "-i", str(first), "-i", str(second), "-filter_complex",
            "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", "18", "-c:a", "aac", str(output),
        ]
    else:
        command = [
            "ffmpeg", "-y", "-i", str(first), "-i", str(second), "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264",
            "-crf", "18", str(output),
        ]
    _run(command, cwd=output.parent)


def _has_audio(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
            "stream=index", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


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


def _write_final_words(
    transcript: Path,
    hook: HookPlan,
    plan: EditPlanV3,
    output: Path,
) -> None:
    ranges = (*hook.segments, *plan.body.keep)
    _write_words_for_ranges(transcript, ranges, output)


def _write_words_for_ranges(
    transcript: Path,
    ranges: Any,
    output: Path,
) -> None:
    words = json.loads(transcript.read_text()).get("words", [])
    selected = [
        word
        for start, end in ranges
        for word in words
        if float(word.get("start", 0.0)) >= start and float(word.get("end", 0.0)) <= end
    ]
    normalized = [
        {"word": word.get("word", ""), "start": index * 0.1, "end": index * 0.1 + 0.08}
        for index, word in enumerate(selected)
    ]
    _write_json(output, {"words": normalized})


def _write_transcript_markdown(transcript: Path, output: Path) -> None:
    words = json.loads(transcript.read_text()).get("words", [])
    output.write_text("# Transcript\n\n" + " ".join(str(word.get("word", "")) for word in words) + "\n")


def _slug(value: str) -> str:
    return "-".join(part for part in "".join(c.lower() if c.isalnum() else " " for c in value).split()) or "angle"
