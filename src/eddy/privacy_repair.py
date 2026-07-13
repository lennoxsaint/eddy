"""Proof-gated visual-only privacy repair for completed Eddy Shorts."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from .caption_repair import (
    _artifact_hashes,
    _audio_stream_sha256,
    _sha256,
    _source_lock_green,
    _write_json,
)
from .runtime import JobManager, JobState


def repair_short_privacy(
    *,
    root: Path,
    manager: JobManager,
    job_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    job = manager.load(job_id)
    if job.state is not JobState.COMPLETED:
        raise RuntimeError(f"privacy_repair_requires_completed_job:{job.state.value}")
    if payload.get("schema_version") != "privacy-repair-v1":
        raise ValueError("privacy_repair_schema_invalid")
    raw_repairs = payload.get("repairs")
    if not isinstance(raw_repairs, list) or not raw_repairs:
        raise ValueError("privacy_repair_rows_required")

    final = job.run_dir / "final"
    validated: list[tuple[str, Path, tuple[dict[str, Any], ...]]] = []
    seen: set[str] = set()
    for row in raw_repairs:
        if not isinstance(row, dict):
            raise ValueError("privacy_repair_row_invalid")
        artifact = row.get("artifact")
        if not isinstance(artifact, str) or not artifact.strip():
            raise ValueError("privacy_repair_artifact_required")
        artifact = artifact.strip()
        relative = Path(artifact)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or len(relative.parts) != 2
            or relative.parts[0] != "shorts"
            or relative.suffix.lower() != ".mp4"
        ):
            raise ValueError("privacy_repair_short_artifact_invalid")
        if artifact in seen:
            raise ValueError("privacy_repair_artifacts_must_be_unique")
        seen.add(artifact)
        delivered = final / relative
        if not delivered.is_file():
            raise FileNotFoundError(f"privacy_repair_artifact_missing:{artifact}")
        width, height, duration = _media_info(delivered)
        masks = _validate_masks(row.get("masks"), width=width, height=height, duration=duration)
        validated.append((artifact, delivered, masks))

    repair = job.run_dir / "repairs" / "privacy-v1"
    if repair.exists():
        raise RuntimeError(f"privacy_repair_already_exists:{repair}")
    originals = repair / "originals"
    candidates = repair / "candidates"
    originals.mkdir(parents=True)
    candidates.mkdir(parents=True)

    long_paths = sorted(final.glob("long-*.mp4"))
    long_hashes_before = {path.name: _sha256(path) for path in long_paths}
    blockers: list[str] = []
    repair_rows: list[dict[str, Any]] = []
    for artifact, delivered, masks in validated:
        original = originals / artifact
        candidate = candidates / artifact
        original.parent.mkdir(parents=True, exist_ok=True)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(delivered, original)
        _render_masks(delivered, candidate, masks, cwd=root)
        before_audio = _audio_stream_sha256(delivered)
        after_audio = _audio_stream_sha256(candidate)
        before_info = _media_info(delivered)
        after_info = _media_info(candidate)
        visual_proof = [
            _mask_visual_proof(candidate, mask, repair / "proof", cwd=root)
            for mask in masks
        ]
        audio_green = before_audio == after_audio
        media_green = (
            before_info[:2] == after_info[:2]
            and abs(before_info[2] - after_info[2]) <= 0.05
        )
        passed = audio_green and media_green and all(row["pass"] for row in visual_proof)
        if not passed:
            blockers.append(f"privacy_repair_gate_failed:{artifact}")
        repair_rows.append(
            {
                "artifact": artifact,
                "pass": passed,
                "masks": list(masks),
                "visual_proof": visual_proof,
                "audio_stream_sha256_before": before_audio,
                "audio_stream_sha256_after": after_audio,
                "audio_stream_identical": audio_green,
                "media_before": {
                    "width": before_info[0],
                    "height": before_info[1],
                    "duration": before_info[2],
                },
                "media_after": {
                    "width": after_info[0],
                    "height": after_info[1],
                    "duration": after_info[2],
                },
                "candidate": str(candidate),
            }
        )

    source_green = _source_lock_green(job.run_dir, job.source, job.snapshot)
    if not source_green:
        blockers.append("source_hash_changed")
    long_hashes_after = {path.name: _sha256(path) for path in long_paths}
    if long_hashes_before != long_hashes_after:
        blockers.append("privacy_repair_changed_long_video")
    if blockers:
        summary = {
            "schema_version": "eddy-privacy-repair-v1",
            "status": "blocked",
            "blockers": list(dict.fromkeys(blockers)),
            "repairs": repair_rows,
            "long_hashes_before": long_hashes_before,
            "long_hashes_after": long_hashes_after,
            "source_lock": source_green,
        }
        _write_json(repair / "repair-summary.json", summary)
        manager.receipt(job_id, "privacy_repair_blocked", blockers=summary["blockers"])
        return summary

    for row in repair_rows:
        os.replace(Path(str(row["candidate"])), final / str(row["artifact"]))

    qa_path = final / "qa.json"
    qa = json.loads(qa_path.read_text()) if qa_path.exists() else {"gates": {}, "shorts": []}
    by_id = {
        Path(str(row["artifact"])).stem.split("-", 1)[-1]: row
        for row in repair_rows
    }
    for short in qa.get("shorts", []):
        repair_row = by_id.get(str(short.get("short")))
        if repair_row:
            short["privacy_masks"] = repair_row["masks"]
            short["privacy_visual_proof"] = repair_row["visual_proof"]
            short["privacy_audio_stream_identical"] = True
            short["pass"] = True
    qa.setdefault("gates", {})["shorts_privacy_masks"] = True
    qa["blockers"] = []
    _write_json(qa_path, qa)

    verification_path = job.run_dir / "verification.json"
    verification = (
        json.loads(verification_path.read_text())
        if verification_path.exists()
        else {"gates": {}, "blockers": []}
    )
    verification.setdefault("gates", {})["shorts_privacy_masks"] = True
    verification["blockers"] = []
    _write_json(verification_path, verification)

    provider_receipts = final / "provider-receipts.jsonl"
    with provider_receipts.open("a") as handle:
        for row in repair_rows:
            handle.write(
                json.dumps(
                    {
                        "event": "short_privacy_visual_repair_audio_reuse",
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
        "schema_version": "eddy-privacy-repair-v1",
        "status": "pass",
        "blockers": [],
        "repairs": repair_rows,
        "long_hashes_before": long_hashes_before,
        "long_hashes_after": long_hashes_after,
        "source_lock": source_green,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _write_json(repair / "repair-summary.json", summary)
    manager.receipt(
        job_id,
        "privacy_repair_completed",
        artifacts=[row["artifact"] for row in repair_rows],
        audio_streams_identical=True,
        long_hashes_unchanged=True,
    )
    return summary


def _validate_masks(
    value: object,
    *,
    width: int,
    height: int,
    duration: float,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or not value or not all(isinstance(row, dict) for row in value):
        raise ValueError("privacy_repair_masks_required")
    masks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        mask_id = raw.get("id")
        if not isinstance(mask_id, str) or not mask_id.strip() or mask_id in seen:
            raise ValueError("privacy_repair_mask_id_invalid")
        seen.add(mask_id)
        try:
            start, end = float(raw["start"]), float(raw["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("privacy_repair_mask_range_invalid") from exc
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0
            or end <= start
            or end > duration + 0.05
        ):
            raise ValueError("privacy_repair_mask_range_invalid")
        coordinates = (raw.get("x"), raw.get("y"), raw.get("width"), raw.get("height"))
        if not all(isinstance(item, int) and not isinstance(item, bool) for item in coordinates):
            raise ValueError("privacy_repair_mask_rectangle_invalid")
        x, y, mask_width, mask_height = coordinates
        assert isinstance(x, int) and isinstance(y, int)
        assert isinstance(mask_width, int) and isinstance(mask_height, int)
        if (
            x < 0
            or y < 0
            or mask_width <= 0
            or mask_height <= 0
            or x + mask_width > width
            or y + mask_height > height
        ):
            raise ValueError("privacy_repair_mask_rectangle_out_of_bounds")
        color = raw.get("color", "0x111827")
        if (
            not isinstance(color, str)
            or len(color) != 8
            or not color.startswith("0x")
            or any(character not in "0123456789abcdefABCDEF" for character in color[2:])
        ):
            raise ValueError("privacy_repair_mask_color_invalid")
        masks.append(
            {
                "id": mask_id.strip(),
                "start": start,
                "end": end,
                "x": x,
                "y": y,
                "width": mask_width,
                "height": mask_height,
                "color": color,
            }
        )
    return tuple(masks)


def _render_masks(
    input_media: Path,
    output_media: Path,
    masks: tuple[dict[str, Any], ...],
    *,
    cwd: Path,
) -> None:
    filters = [
        (
            f"drawbox=x={mask['x']}:y={mask['y']}:w={mask['width']}:h={mask['height']}:"
            f"color={mask['color']}:t=fill:"
            f"enable='between(t,{mask['start']:.3f},{mask['end']:.3f})'"
        )
        for mask in masks
    ]
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
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
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not output_media.exists():
        raise RuntimeError(f"privacy_repair_render_failed:{result.stderr[-800:]}")


def _mask_visual_proof(
    media: Path,
    mask: dict[str, Any],
    proof_dir: Path,
    *,
    cwd: Path,
) -> dict[str, Any]:
    proof_dir.mkdir(parents=True, exist_ok=True)
    frame = proof_dir / f"{Path(media).stem}-{mask['id']}.png"
    timestamp = (float(mask["start"]) + float(mask["end"])) / 2
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(media),
            "-frames:v",
            "1",
            str(frame),
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not frame.exists():
        return {"id": mask["id"], "pass": False, "reason": "proof_frame_missing"}
    image = Image.open(frame).convert("RGB")
    center_x = int(mask["x"]) + int(mask["width"]) // 2
    center_y = int(mask["y"]) + int(mask["height"]) // 2
    pixel_raw = image.getpixel((center_x, center_y))
    if not isinstance(pixel_raw, tuple) or len(pixel_raw) < 3:
        return {"id": mask["id"], "pass": False, "reason": "proof_pixel_invalid"}
    pixel = (int(pixel_raw[0]), int(pixel_raw[1]), int(pixel_raw[2]))
    expected = tuple(int(str(mask["color"])[index:index + 2], 16) for index in (2, 4, 6))
    delta = max(abs(pixel[index] - expected[index]) for index in range(3))
    return {
        "id": mask["id"],
        "pass": delta <= 8,
        "timestamp": timestamp,
        "sample_pixel": list(pixel),
        "expected_pixel": list(expected),
        "max_channel_delta": delta,
        "frame": str(frame),
    }


def _media_info(media: Path) -> tuple[int, int, float]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(media),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"privacy_repair_probe_failed:{result.stderr[-500:]}")
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    return int(stream["width"]), int(stream["height"]), float(payload["format"]["duration"])
