"""Proof-gated visual-only caption repair for completed Eddy runs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .pipeline import (
    _read_motion_context_proof,
    _slug,
    _transcribe_final,
    discover_sources,
)
from .plan import EditPlanV3
from .proof import (
    caption_sync_verdict,
    caption_terminal_punctuation_verdict,
    contextual_motion_verdict,
    measure_motion_activity,
    screen_proof_verdict,
)
from .runtime import JobManager, JobState, REQUIRED_FINAL_GATES


def repair_captions(*, root: Path, manager: JobManager, job_id: str) -> dict[str, Any]:
    job = manager.load(job_id)
    if job.state is not JobState.COMPLETED:
        raise RuntimeError(f"caption_repair_requires_completed_job:{job.state.value}")
    final = job.run_dir / "final"
    stage = job.run_dir / "work" / "stage-1"
    plan = EditPlanV3.from_dict(json.loads((job.run_dir / "edit-plan.json").read_text()))
    repair = job.run_dir / "repairs" / "caption-punctuation-v1"
    if repair.exists():
        raise RuntimeError(f"caption_repair_already_exists:{repair}")
    originals = repair / "originals"
    candidates = repair / "candidates"
    originals.mkdir(parents=True)
    candidates.mkdir(parents=True)

    long_paths = sorted(final.glob("long-*.mp4"))
    long_hashes_before = {path.name: _sha256(path) for path in long_paths}
    sources = discover_sources(job.snapshot)
    provider_receipts = final / "provider-receipts.jsonl"
    qa = json.loads((final / "qa.json").read_text())
    verification = json.loads((job.run_dir / "verification.json").read_text())
    blockers: list[str] = []
    repaired_rows: list[dict[str, Any]] = []

    for index, short in enumerate(plan.shorts, start=1):
        short_id = _slug(short.id)
        artifact = f"shorts/{index:02d}-{short_id}.mp4"
        delivered = final / artifact
        composite = stage / f"short-{short_id}-composite.mp4"
        overlay = stage / f"short-{short_id}-motion-overlay.mp4"
        words_path = stage / f"short-{short_id}-words.json"
        segment_receipt = stage / f"short-{short_id}-camera.segments.json"
        required = (delivered, composite, overlay, words_path, segment_receipt)
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            blockers.append(f"caption_repair_intermediate_missing:{short_id}:{','.join(missing)}")
            continue

        original = originals / delivered.name
        shutil.copy2(delivered, original)
        ass = candidates / f"short-{short_id}.ass"
        punctuation_path = candidates / f"short-{short_id}-caption-punctuation.json"
        captioned = candidates / f"short-{short_id}-captioned.mp4"
        motioned = candidates / f"short-{short_id}-motioned.mp4"
        candidate = candidates / delivered.name
        final_words = candidates / f"short-{short_id}-final-words.json"
        planned_words = json.loads(words_path.read_text()).get("words", [])

        _run(
            [
                sys.executable,
                str(root / "scripts" / "karaoke_ass.py"),
                "--transcript",
                str(words_path),
                "--out",
                str(ass),
                "--proof-out",
                str(punctuation_path),
                "--burn",
                "--in",
                str(composite),
                "--video-out",
                str(captioned),
                "--max-words",
                "5",
            ],
            cwd=root,
        )
        _composite_existing_motion(captioned, overlay, motioned, cwd=root)
        _remux_proven_audio(motioned, delivered, candidate, cwd=root)

        before_audio = _audio_stream_sha256(delivered)
        after_audio = _audio_stream_sha256(candidate)
        punctuation = caption_terminal_punctuation_verdict(
            planned_words,
            json.loads(punctuation_path.read_text()).get("rendered_tokens", []),
        )
        audio_green = before_audio == after_audio
        _transcribe_final(root, candidate, final_words)
        caption_sync = caption_sync_verdict(
            planned_words,
            json.loads(final_words.read_text()).get("words", []),
        )
        verify = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "verify.py"),
                "--final",
                str(candidate),
                "--final-words",
                str(final_words),
                "--plan",
                str(job.run_dir / "edit-plan.json"),
                "--editorial-ledger",
                str(job.run_dir / "editorial-ledger.json"),
                "--segments",
                str(segment_receipt),
                "--sacred",
                str(stage / f"short-{short_id}-cutlist.json"),
                "--expect-w",
                "1080",
                "--expect-h",
                "1920",
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )
        motion_activity = measure_motion_activity(overlay, short.motion_beats)
        placement = _read_motion_context_proof(
            stage / f"motion-short-{short_id}" / "shorts-card" / "placement-proof.json",
            expected_beats=len(short.motion_beats),
        )
        motion_context = contextual_motion_verdict(overlay, placement)
        screen_proof = (
            screen_proof_verdict(
                candidate,
                sources.screen,
                segment_receipt,
                short.screen_proof_segments,
                excluded_final_ranges=tuple(
                    (float(beat["start"]), float(beat["start"]) + float(beat["dur"]))
                    for beat in short.motion_beats
                ),
            )
            if sources.screen is not None
            else {"pass": True, "screen_share": 1.0, "samples": []}
        )
        passed = all(
            (
                audio_green,
                bool(punctuation["pass"]),
                bool(caption_sync["pass"]),
                verify.returncode == 0,
                bool(motion_activity["pass"]),
                bool(motion_context["pass"]),
                bool(screen_proof["pass"]),
            )
        )
        if not passed:
            blockers.append(f"caption_repair_gate_failed:{short_id}")
        repaired_rows.append(
            {
                "short": short.id,
                "artifact": artifact,
                "pass": passed,
                "audio_stream_sha256_before": before_audio,
                "audio_stream_sha256_after": after_audio,
                "audio_stream_identical": audio_green,
                "caption_sync": caption_sync,
                "caption_terminal_punctuation": punctuation,
                "motion_activity": motion_activity,
                "motion_context": motion_context,
                "screen_proof": screen_proof,
                "deterministic_qa": {
                    "pass": verify.returncode == 0,
                    "stdout_tail": verify.stdout[-1200:],
                    "stderr_tail": verify.stderr[-1200:],
                },
                "candidate": str(candidate),
            }
        )

    source_green = _source_lock_green(job.run_dir, job.source, job.snapshot)
    if not source_green:
        blockers.append("source_hash_changed")
    long_hashes_after = {path.name: _sha256(path) for path in long_paths}
    if long_hashes_before != long_hashes_after:
        blockers.append("caption_repair_changed_long_video")
    if len(repaired_rows) != len(plan.shorts):
        blockers.append("caption_repair_short_count_mismatch")
    if blockers:
        summary = {
            "schema_version": "eddy-caption-repair-v1",
            "status": "blocked",
            "blockers": list(dict.fromkeys(blockers)),
            "shorts": repaired_rows,
            "long_hashes_before": long_hashes_before,
            "long_hashes_after": long_hashes_after,
            "source_lock": source_green,
        }
        _write_json(repair / "repair-summary.json", summary)
        manager.receipt(job_id, "caption_repair_blocked", blockers=summary["blockers"])
        return summary

    for row in repaired_rows:
        target = final / str(row["artifact"])
        candidate = Path(str(row["candidate"]))
        os.replace(candidate, target)

    by_short = {str(row["short"]): row for row in repaired_rows}
    for row in qa.get("shorts", []):
        repaired = by_short.get(str(row.get("short")))
        if repaired:
            row.update(
                {
                    "caption_sync": repaired["caption_sync"],
                    "caption_terminal_punctuation": repaired["caption_terminal_punctuation"],
                    "motion_activity": repaired["motion_activity"],
                    "motion_context": repaired["motion_context"],
                    "screen_proof": repaired["screen_proof"],
                    "pass": True,
                }
            )
    qa.setdefault("gates", {})["caption_terminal_punctuation"] = True
    qa["blockers"] = []
    verification.setdefault("gates", {})["caption_terminal_punctuation"] = True
    verification["blockers"] = []
    missing = sorted(REQUIRED_FINAL_GATES - set(verification["gates"]))
    if missing or not all(verification["gates"].values()):
        raise RuntimeError(f"caption_repair_post_promotion_gate_invalid:{','.join(missing)}")
    _write_json(final / "qa.json", qa)
    _write_json(job.run_dir / "verification.json", verification)

    with provider_receipts.open("a") as handle:
        for row in repaired_rows:
            handle.write(
                json.dumps(
                    {
                        "event": "caption_visual_repair_audio_reuse",
                        "artifact": row["artifact"],
                        "status": "pass",
                        "audio_stream_sha256": row["audio_stream_sha256_after"],
                        "provider_proof": "existing_descript_effect_survival",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    _write_json(final / "artifact-manifest.json", {"files": _artifact_hashes(final)})
    summary = {
        "schema_version": "eddy-caption-repair-v1",
        "status": "pass",
        "blockers": [],
        "shorts": repaired_rows,
        "long_hashes_before": long_hashes_before,
        "long_hashes_after": long_hashes_after,
        "source_lock": source_green,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _write_json(repair / "repair-summary.json", summary)
    manager.receipt(
        job_id,
        "caption_repair_completed",
        audio_streams_identical=True,
        shorts=len(repaired_rows),
        long_hashes_unchanged=True,
    )
    return summary


def _composite_existing_motion(base: Path, overlay: Path, output: Path, *, cwd: Path) -> None:
    filters = (
        "[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "format=rgba,colorkey=0x000000:0.10:0.12,colorchannelmixer=aa=0.94[ov];"
        "[0:v][ov]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(base),
            "-i",
            str(overlay),
            "-filter_complex",
            filters,
            "-map",
            "[v]",
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
            str(output),
        ],
        cwd=cwd,
    )


def _remux_proven_audio(video: Path, proven: Path, output: Path, *, cwd: Path) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-i",
            str(proven),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ],
        cwd=cwd,
    )


def _audio_stream_sha256(media: Path) -> str:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(media),
            "-map",
            "0:a:0",
            "-c",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or "SHA256=" not in result.stdout:
        raise RuntimeError(f"audio_stream_hash_failed:{media}:{result.stderr[-500:]}")
    return result.stdout.strip().split("SHA256=", 1)[1]


def _source_lock_green(run_dir: Path, source: Path, snapshot: Path) -> bool:
    lock = json.loads((run_dir / "source-lock.json").read_text())
    before = dict(lock.get("before", {}))
    expected_snapshot = dict(lock.get("snapshot", {}))
    current = {
        relative: _sha256(source if source.is_file() else source / relative)
        for relative in before
    }
    snapshot_current = {relative: _sha256(snapshot / relative) for relative in before}
    return current == before and snapshot_current == expected_snapshot


def _artifact_hashes(final: Path) -> dict[str, str]:
    return {
        path.relative_to(final).as_posix(): _sha256(path)
        for path in sorted(final.rglob("*"))
        if path.is_file() and path.name != "artifact-manifest.json"
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _run(command: list[str], *, cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "blocker": "caption_repair_command_failed",
                    "command": command,
                    "stderr": result.stderr[-1200:],
                }
            )
        )
