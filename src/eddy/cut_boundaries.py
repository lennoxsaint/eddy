"""Deterministic cut-boundary inspection and silent-handle repair planning."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MAX_UNEXPLAINED_INSERT_FRAMES = 6
SILENT_HANDLE_MAX_SECONDS = 0.24
SILENT_HANDLE_MAX_DBFS = -40.0


class CutBoundaryError(ValueError):
    """A boundary manifest is malformed or contains unresolved micro-shots."""


def audit_timeline(value: object) -> dict[str, Any]:
    """Audit source-mapped timeline segments without inventing visual intent."""

    if not isinstance(value, dict) or value.get("schema_version") != "eddy-cut-boundary-manifest-v1":
        raise CutBoundaryError("cut_boundary_manifest_schema_invalid")
    fps = value.get("fps")
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0:
        raise CutBoundaryError("cut_boundary_fps_invalid")
    rows = value.get("segments")
    if not isinstance(rows, list) or not rows:
        raise CutBoundaryError("cut_boundary_segments_required")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise CutBoundaryError(f"cut_boundary_segment_invalid:{index}")
        segment_id = _text(raw.get("id"), f"cut_boundary_segment_id_required:{index}")
        source_id = _text(raw.get("source_id"), f"cut_boundary_source_id_required:{segment_id}")
        try:
            start = float(raw["timeline_start"])
            end = float(raw["timeline_end"])
            rms_dbfs = float(raw["rms_dbfs"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CutBoundaryError(f"cut_boundary_segment_measurement_invalid:{segment_id}") from exc
        if start < 0 or end <= start:
            raise CutBoundaryError(f"cut_boundary_segment_range_invalid:{segment_id}")
        protected = raw.get("protected", False)
        if not isinstance(protected, bool):
            raise CutBoundaryError(f"cut_boundary_protected_invalid:{segment_id}")
        if protected and not _text(
            raw.get("protected_reason"),
            f"cut_boundary_protected_reason_required:{segment_id}",
        ):
            raise CutBoundaryError(f"cut_boundary_protected_reason_required:{segment_id}")
        protected_evidence_ref = raw.get("protected_evidence_ref")
        if protected and not _text(
            protected_evidence_ref,
            f"cut_boundary_protected_evidence_required:{segment_id}",
        ):
            raise CutBoundaryError(f"cut_boundary_protected_evidence_required:{segment_id}")
        protected_evidence_sha256 = raw.get("protected_evidence_sha256")
        if protected and not _valid_hash(protected_evidence_sha256):
            raise CutBoundaryError(
                f"cut_boundary_protected_evidence_hash_required:{segment_id}"
            )
        if protected and raw.get("protected_evidence_purpose_specific") is not True:
            raise CutBoundaryError(
                f"cut_boundary_protected_evidence_purpose_required:{segment_id}"
            )
        if protected and raw.get("protected_evidence_self_attested") is not False:
            raise CutBoundaryError(
                f"cut_boundary_protected_evidence_independence_required:{segment_id}"
            )
        normalized.append(
            {
                "id": segment_id,
                "source_id": source_id,
                "timeline_start": start,
                "timeline_end": end,
                "duration_seconds": end - start,
                "duration_frames": round((end - start) * float(fps)),
                "rms_dbfs": rms_dbfs,
                "protected": protected,
                "protected_reason": raw.get("protected_reason"),
                "protected_evidence_ref": protected_evidence_ref,
                "protected_evidence_sha256": protected_evidence_sha256,
            }
        )

    candidates: list[dict[str, Any]] = []
    dropped: list[str] = []
    for index, row in enumerate(normalized):
        silent_handle = (
            row["duration_seconds"] < SILENT_HANDLE_MAX_SECONDS
            and row["rms_dbfs"] < SILENT_HANDLE_MAX_DBFS
        )
        micro_insert = False
        pattern = None
        if 0 < index < len(normalized) - 1 and 1 <= row["duration_frames"] <= 6:
            before = normalized[index - 1]
            after = normalized[index + 1]
            micro_insert = row["source_id"] not in {before["source_id"], after["source_id"]}
            if micro_insert:
                pattern = "a_b_a" if before["source_id"] == after["source_id"] else "third_shot"
        if not silent_handle and not micro_insert:
            continue
        candidate = {
            "segment_id": row["id"],
            "pattern": pattern or "silent_residual_handle",
            "duration_frames": row["duration_frames"],
            "duration_seconds": round(row["duration_seconds"], 6),
            "rms_dbfs": row["rms_dbfs"],
            "protected": row["protected"],
            "decision": "protected" if row["protected"] else "drop",
            "reason": row["protected_reason"] if row["protected"] else "unexplained_boundary_residue",
            "protected_evidence_ref": row["protected_evidence_ref"],
        }
        candidates.append(candidate)
        if not row["protected"]:
            dropped.append(row["id"])

    return {
        "schema_version": "eddy-cut-boundary-audit-v1",
        "fps": float(fps),
        "decoder_policy": "fps_mode_passthrough",
        "frame_window_each_side": 8,
        "boundary_supercut_speed": 0.25,
        "thresholds": {
            "micro_insert_frames": [1, 6],
            "silent_handle_max_seconds": SILENT_HANDLE_MAX_SECONDS,
            "silent_handle_max_dbfs": SILENT_HANDLE_MAX_DBFS,
        },
        "boundaries": [
            {
                "id": f"boundary-{index:04d}",
                "at_seconds": row["timeline_start"],
                "before_segment_id": normalized[index - 1]["id"],
                "after_segment_id": row["id"],
                "strip_start_seconds": max(
                    0.0,
                    row["timeline_start"] - 8 / float(fps),
                ),
                "strip_end_seconds": row["timeline_start"] + 8 / float(fps),
            }
            for index, row in enumerate(normalized[1:], start=1)
        ],
        "candidates": candidates,
        "drop_segment_ids": dropped,
        "kept_segment_ids": [row["id"] for row in normalized if row["id"] not in dropped],
        "unresolved": [row for row in candidates if row["decision"] == "drop"],
        "pass": not dropped,
    }


def boundary_review_commands(
    media: Path,
    audit: dict[str, Any],
    output_dir: Path,
) -> tuple[list[list[str]], list[str]]:
    """Build non-duplicating ffmpeg commands for frame strips and a 0.25x supercut."""

    boundaries = audit.get("boundaries")
    if not isinstance(boundaries, list) or not boundaries:
        raise CutBoundaryError("cut_boundary_review_boundaries_required")
    frame_window = audit.get("frame_window_each_side")
    if frame_window != 8 or audit.get("boundary_supercut_speed") != 0.25:
        raise CutBoundaryError("cut_boundary_review_contract_invalid")
    output_dir = output_dir.resolve()
    strip_dir = output_dir / "frame-strips"
    commands: list[list[str]] = []
    outputs: list[str] = []
    for row in boundaries:
        if not isinstance(row, dict):
            raise CutBoundaryError("cut_boundary_review_boundary_invalid")
        boundary_id = _text(
            row.get("id"),
            "cut_boundary_review_boundary_id_required",
        )
        start = float(row["strip_start_seconds"])
        end = float(row["strip_end_seconds"])
        strip = strip_dir / f"{boundary_id}.png"
        commands.append(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.6f}",
                "-i",
                str(media.resolve()),
                "-t",
                f"{end - start:.6f}",
                "-vf",
                "scale=320:-2,tile=17x1",
                "-frames:v",
                "1",
                "-fps_mode",
                "passthrough",
                str(strip),
            ]
        )
        outputs.append(strip.relative_to(output_dir).as_posix())

    filter_parts: list[str] = []
    for index, row in enumerate(boundaries):
        start = float(row["strip_start_seconds"])
        end = float(row["strip_end_seconds"])
        filter_parts.append(
            f"[0:v]trim=start={start:.6f}:end={end:.6f},"
            f"setpts=4*(PTS-STARTPTS)[v{index}]"
        )
    stack = "".join(f"[v{index}]" for index in range(len(boundaries)))
    filter_parts.append(f"{stack}concat=n={len(boundaries)}:v=1:a=0[outv]")
    supercut = output_dir / "boundary-supercut-0.25x.mp4"
    commands.append(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(media.resolve()),
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[outv]",
            "-an",
            "-fps_mode",
            "passthrough",
            str(supercut),
        ]
    )
    outputs.append(supercut.relative_to(output_dir).as_posix())
    return commands, outputs


def _text(value: object, error: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CutBoundaryError(error)
    return value.strip()


def _valid_hash(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )
