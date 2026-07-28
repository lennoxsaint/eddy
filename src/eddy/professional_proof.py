"""Hash-bound objective proof for professional VSL candidate promotion."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


REQUIRED_PROFESSIONAL_GATES = {
    "content_hash_cache_keys",
    "sample_exact_splices",
    "sequence_search_parity",
    "waveform_cut_authority",
    "shot_entry_latency",
    "word_edges_protected",
    "delivered_retranscription",
    "motion_full_segment_coverage",
    "motion_no_frozen_tails",
    "motion_no_frame_flashes",
    "crop_and_annotation_targets",
    "factual_bindings",
    "reconstruction_provenance",
    "studio_sound_lineage",
    "studio_sound_effect_survival",
    "audio_mix",
    "shorts_music_variation",
    "camera_grade",
    "screen_color_fidelity",
    "shorts_progressive_captions",
    "shorts_speaker_attribution",
    "long_caption_policy",
    "three_longs_shared_body",
    "shorts_non_padding",
}

ALLOWED_EVIDENCE_TYPES = {
    "file",
    "frame",
    "timestamp",
    "hash",
    "playback",
    "measurement",
}


def validate_professional_gate_receipt(
    attempt: Path,
    value: object,
) -> dict[str, bool]:
    """Require every known defect class to point at immutable local evidence."""

    if not isinstance(value, dict) or value.get("schema_version") != "eddy-professional-gates-v1":
        raise ValueError("professional_gates_schema_invalid")
    gates = value.get("gates")
    if not isinstance(gates, dict) or set(gates) != REQUIRED_PROFESSIONAL_GATES:
        raise ValueError("professional_gates_set_invalid")
    result: dict[str, bool] = {}
    for gate_id in sorted(REQUIRED_PROFESSIONAL_GATES):
        row = gates[gate_id]
        if not isinstance(row, dict) or row.get("passed") is not True:
            raise ValueError(f"professional_gate_failed:{gate_id}")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"professional_gate_evidence_required:{gate_id}")
        for item in evidence:
            _validate_evidence(attempt, item, gate_id)
        result[gate_id] = True
    return result


def validate_verifier_review(attempt: Path, value: object) -> dict[str, Any]:
    """Validate a no-edit verifier's complete watch/listen coverage."""

    if not isinstance(value, dict) or value.get("schema_version") != "verifier-review-v1":
        raise ValueError("verifier_review_schema_invalid")
    if value.get("authority") != "independent_no_edit_context":
        raise ValueError("verifier_authority_invalid")
    if value.get("edit_authority") is not False:
        raise ValueError("verifier_must_not_have_edit_authority")
    if value.get("promotion_recommendation") != "objective_green":
        raise ValueError("verifier_objective_green_required")
    outputs = value.get("outputs")
    if not isinstance(outputs, list):
        raise ValueError("verifier_outputs_invalid")
    delivered = _delivered_outputs(attempt)
    reviewed_refs = {
        str(row.get("ref"))
        for row in outputs
        if isinstance(row, dict) and isinstance(row.get("ref"), str)
    }
    expected_refs = {path.relative_to(attempt).as_posix() for path in delivered}
    if reviewed_refs != expected_refs or not 3 <= len(
        [ref for ref in reviewed_refs if ref.startswith("shorts/")]
    ) <= 5:
        raise ValueError("verifier_output_coverage_incomplete")
    if len([ref for ref in reviewed_refs if ref.startswith("long-")]) != 3:
        raise ValueError("verifier_output_coverage_incomplete")
    for row in outputs:
        if not isinstance(row, dict):
            raise ValueError("verifier_output_invalid")
        ref = str(row["ref"])
        path = attempt / ref
        if (
            row.get("sha256") != _sha256(path)
            or row.get("full_watch") is not True
            or row.get("full_listen") is not True
        ):
            raise ValueError(f"verifier_output_proof_invalid:{ref}")
        try:
            duration = float(row["duration_seconds"])
            watched = float(row["watched_seconds"])
            listened = float(row["listened_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"verifier_output_duration_invalid:{ref}") from exc
        if duration <= 0 or watched + 0.05 < duration or listened + 0.05 < duration:
            raise ValueError(f"verifier_output_playback_incomplete:{ref}")
        if row.get("defects") != []:
            raise ValueError(f"verifier_output_defects_unresolved:{ref}")
    return {"output_count": len(outputs), "output_refs": sorted(reviewed_refs)}


def validate_open_items(value: object) -> dict[str, Any]:
    """Allow optional taste alternatives while rejecting unresolved objective defects."""

    if not isinstance(value, dict) or value.get("schema_version") != "eddy-open-items-v1":
        raise ValueError("open_items_schema_invalid")
    objective = value.get("objective")
    subjective = value.get("subjective_optional")
    if not isinstance(objective, list) or not isinstance(subjective, list):
        raise ValueError("open_items_lists_invalid")
    if objective:
        raise ValueError("objective_open_items_must_be_empty")
    for row in subjective:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not row["id"].strip()
            or not isinstance(row.get("description"), str)
            or not row["description"].strip()
        ):
            raise ValueError("subjective_open_item_invalid")
    return {"objective": objective, "subjective_optional": subjective}


def _validate_evidence(attempt: Path, value: object, gate_id: str) -> None:
    if not isinstance(value, dict) or value.get("type") not in ALLOWED_EVIDENCE_TYPES:
        raise ValueError(f"professional_gate_evidence_invalid:{gate_id}")
    ref = value.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"professional_gate_evidence_ref_invalid:{gate_id}")
    base = ref.split("#", 1)[0]
    path_ref = Path(base)
    if path_ref.is_absolute() or ".." in path_ref.parts:
        raise ValueError(f"professional_gate_evidence_ref_invalid:{gate_id}")
    path = attempt / path_ref
    if not path.is_file():
        raise ValueError(f"professional_gate_evidence_missing:{gate_id}")
    if value.get("sha256") != _sha256(path):
        raise ValueError(f"professional_gate_evidence_hash_mismatch:{gate_id}")


def _delivered_outputs(attempt: Path) -> list[Path]:
    longs = sorted(
        path
        for path in attempt.glob("long-*.mp4")
        if path.is_file()
    )
    shorts = sorted(
        path
        for path in (attempt / "shorts").glob("*.mp4")
        if path.is_file()
    ) if (attempt / "shorts").is_dir() else []
    return [*longs, *shorts]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
