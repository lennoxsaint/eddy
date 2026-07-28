"""Deterministic validators for the recurring VSL failure classes."""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def content_addressed_cache_key(
    source: Path,
    *,
    namespace: str,
    parameters: dict[str, Any] | None = None,
) -> str:
    """Key derived work by bytes and settings, never by a mutable filename."""

    if not namespace.strip():
        raise ValueError("cache_namespace_required")
    payload = {
        "schema_version": "eddy-content-cache-key-v1",
        "namespace": namespace,
        "source_sha256": _sha256(source),
        "parameters": parameters or {},
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sequence_search_parity(
    expected: bytes,
    delivered: bytes,
    *,
    max_offset_bytes: int = 0,
) -> dict[str, Any]:
    """Prove an expected PCM/sample sequence occurs once at a bounded offset."""

    if not expected:
        raise ValueError("sequence_expected_empty")
    if max_offset_bytes < 0:
        raise ValueError("sequence_max_offset_invalid")
    offsets: list[int] = []
    cursor = delivered.find(expected)
    while cursor >= 0:
        offsets.append(cursor)
        cursor = delivered.find(expected, cursor + 1)
    passed = len(offsets) == 1 and offsets[0] <= max_offset_bytes
    return {
        "schema_version": "eddy-sequence-parity-v1",
        "pass": passed,
        "expected_sha256": hashlib.sha256(expected).hexdigest(),
        "delivered_sha256": hashlib.sha256(delivered).hexdigest(),
        "match_count": len(offsets),
        "offset_bytes": offsets[0] if len(offsets) == 1 else None,
        "max_offset_bytes": max_offset_bytes,
        "reason": None if passed else "sample_sequence_parity_failed",
    }


def shot_entry_latency_verdict(
    rows: list[dict[str, Any]],
    *,
    frame_rate: float,
    max_frames: int = 2,
) -> dict[str, Any]:
    """Reject perceptible shot-to-speech gaps unless the plan protects the pause."""

    if frame_rate <= 0 or max_frames < 0:
        raise ValueError("shot_entry_latency_settings_invalid")
    measured: list[dict[str, Any]] = []
    for row in rows:
        shot_id = str(row.get("shot_id", "")).strip() or "unknown"
        try:
            shot_start = float(row["shot_start_seconds"])
            speech_onset = float(row["speech_onset_seconds"])
        except (KeyError, TypeError, ValueError):
            measured.append(
                {"shot_id": shot_id, "pass": False, "reason": "timing_missing"}
            )
            continue
        frames = (speech_onset - shot_start) * frame_rate
        protected = bool(row.get("protected_exception"))
        passed = protected or 0 <= frames <= max_frames
        measured.append(
            {
                "shot_id": shot_id,
                "latency_frames": round(frames, 4),
                "protected_exception": protected,
                "exception_id": row.get("exception_id"),
                "pass": passed,
                "reason": (
                    None
                    if passed
                    else (
                        "speech_precedes_shot_without_exception"
                        if frames < 0
                        else "shot_entry_speech_delay"
                    )
                ),
            }
        )
    return {
        "schema_version": "eddy-shot-entry-latency-v1",
        "pass": bool(measured) and all(row["pass"] for row in measured),
        "frame_rate": frame_rate,
        "max_frames": max_frames,
        "shots": measured,
    }


def word_edge_protection_verdict(
    planned_words: list[dict[str, Any]],
    delivered_words: list[dict[str, Any]],
    *,
    tolerance_seconds: float = 0.04,
) -> dict[str, Any]:
    """Catch clipped leading phonemes and word endings after every splice/retime."""

    if tolerance_seconds < 0:
        raise ValueError("word_edge_tolerance_invalid")
    planned_tokens = [_token(row.get("word")) for row in planned_words]
    delivered_tokens = [_token(row.get("word")) for row in delivered_words]
    matcher = SequenceMatcher(a=planned_tokens, b=delivered_tokens, autojunk=False)
    pairs: list[tuple[int, int]] = []
    for block in matcher.get_matching_blocks():
        pairs.extend(
            (block.a + offset, block.b + offset)
            for offset in range(block.size)
        )
    issues: list[dict[str, Any]] = []
    for planned_index, delivered_index in pairs:
        planned = planned_words[planned_index]
        delivered = delivered_words[delivered_index]
        onset_loss = float(delivered["start"]) - float(planned["start"])
        ending_loss = float(planned["end"]) - float(delivered["end"])
        if onset_loss > tolerance_seconds or ending_loss > tolerance_seconds:
            issues.append(
                {
                    "word": planned.get("word"),
                    "planned_index": planned_index,
                    "delivered_index": delivered_index,
                    "onset_loss_seconds": round(onset_loss, 4),
                    "ending_loss_seconds": round(ending_loss, 4),
                }
            )
    matched_ratio = len(pairs) / max(1, len(planned_tokens), len(delivered_tokens))
    passed = (
        len(planned_tokens) == len(delivered_tokens)
        and matched_ratio == 1.0
        and not issues
    )
    return {
        "schema_version": "eddy-word-edge-protection-v1",
        "pass": passed,
        "matched_ratio": round(matched_ratio, 4),
        "issues": issues,
        "reason": None if passed else "delivered_word_edge_loss",
    }


def motion_segment_coverage_verdict(
    rows: list[dict[str, Any]],
    *,
    frame_rate: float,
    edge_tolerance_frames: int = 1,
) -> dict[str, Any]:
    """Reject motion that ends early, freezes at the tail, or flashes for one frame."""

    if frame_rate <= 0 or edge_tolerance_frames < 0:
        raise ValueError("motion_coverage_settings_invalid")
    tolerance = edge_tolerance_frames / frame_rate
    measured: list[dict[str, Any]] = []
    for row in rows:
        segment_id = str(row.get("segment_id", "")).strip() or "unknown"
        try:
            intended_start = float(row["intended_start_seconds"])
            intended_end = float(row["intended_end_seconds"])
            first_active = float(row["first_active_seconds"])
            last_active = float(row["last_active_seconds"])
            frozen_tail = int(row.get("trailing_frozen_frames", 0))
            flashes = int(row.get("one_frame_flashes", 0))
        except (KeyError, TypeError, ValueError):
            measured.append(
                {"segment_id": segment_id, "pass": False, "reason": "measurement_missing"}
            )
            continue
        coverage = (
            first_active <= intended_start + tolerance
            and last_active >= intended_end - tolerance
        )
        passed = coverage and frozen_tail == 0 and flashes == 0
        measured.append(
            {
                "segment_id": segment_id,
                "coverage_complete": coverage,
                "trailing_frozen_frames": frozen_tail,
                "one_frame_flashes": flashes,
                "pass": passed,
                "reason": None if passed else "motion_segment_defect",
            }
        )
    return {
        "schema_version": "eddy-motion-coverage-v1",
        "pass": bool(measured) and all(row["pass"] for row in measured),
        "segments": measured,
    }


def progressive_caption_verdict(
    cues: list[dict[str, Any]],
    *,
    multi_speaker: bool,
) -> dict[str, Any]:
    """Prove prior words remain, the active word highlights, and future words hide."""

    failures: list[dict[str, Any]] = []
    speaker_styles: dict[str, tuple[str, str]] = {}
    for index, cue in enumerate(cues):
        prior = [str(word) for word in cue.get("prior_words", [])]
        active = str(cue.get("active_word", ""))
        visible = [str(word) for word in cue.get("visible_words", [])]
        future = cue.get("future_words_visible")
        future_hidden = future is False or future is None or future == []
        passed = bool(active) and visible == [*prior, active] and future_hidden
        speaker_id = str(cue.get("speaker_id", "")).strip()
        label = str(cue.get("speaker_label", "")).strip()
        color = str(cue.get("speaker_color", "")).strip()
        if multi_speaker:
            passed = passed and bool(speaker_id and label and color)
            style = (label, color)
            if speaker_id in speaker_styles and speaker_styles[speaker_id] != style:
                passed = False
            elif speaker_id:
                speaker_styles[speaker_id] = style
        if not passed:
            failures.append({"cue_index": index, "speaker_id": speaker_id or None})
    return {
        "schema_version": "eddy-progressive-caption-proof-v1",
        "pass": bool(cues) and not failures,
        "cue_count": len(cues),
        "failures": failures,
    }


def shared_body_hash_verdict(
    body_hashes: dict[str, str],
    *,
    expected_variants: int = 3,
) -> dict[str, Any]:
    """Require all Long variants to share one byte-identical rendered body."""

    valid = (
        len(body_hashes) == expected_variants
        and all(re.fullmatch(r"[0-9a-f]{64}", value) for value in body_hashes.values())
    )
    unique = set(body_hashes.values()) if valid else set()
    return {
        "schema_version": "eddy-shared-body-proof-v1",
        "pass": valid and len(unique) == 1,
        "variant_count": len(body_hashes),
        "unique_body_hashes": len(unique),
    }


def _token(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
