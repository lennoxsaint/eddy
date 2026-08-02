"""Hash-bound objective proof for professional VSL candidate promotion."""

from __future__ import annotations

import hashlib
import json
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

REQUIRED_PROFESSIONAL_GATES_V2 = (
    REQUIRED_PROFESSIONAL_GATES
    - {"three_longs_shared_body"}
) | {
    "long_routes_shared_body",
    "cut_boundary_integrity",
    "complete_clause_recovery",
    "source_audio_recovery",
    "caption_override_accuracy",
    "readable_screen_context",
    "talking_head_geometry",
}

GATE_EVALUATORS = {
    gate_id: f"eddy-{gate_id.replace('_', '-')}-evaluator-v1"
    for gate_id in REQUIRED_PROFESSIONAL_GATES_V2
}

GATE_METRIC_REQUIREMENTS: dict[str, dict[str, Any]] = {
    gate_id: {
        "evaluated_by": GATE_EVALUATORS[gate_id],
        "sample_count_min": 1,
        "failures": 0,
    }
    for gate_id in REQUIRED_PROFESSIONAL_GATES_V2
}
GATE_METRIC_REQUIREMENTS.update(
    {
        "cut_boundary_integrity": {
            **GATE_METRIC_REQUIREMENTS["cut_boundary_integrity"],
            "unresolved_count": 0,
            "drop_candidate_count": 0,
            "decoder_policy": "fps_mode_passthrough",
            "frame_window_each_side": 8,
            "supercut_speed": 0.25,
        },
        "complete_clause_recovery": {
            **GATE_METRIC_REQUIREMENTS["complete_clause_recovery"],
            "clipped_clause_count": 0,
            "source_exact_word_endings": True,
        },
        "source_audio_recovery": {
            **GATE_METRIC_REQUIREMENTS["source_audio_recovery"],
            "missing_declared_intervals": 0,
            "synthesized_reply_count": 0,
        },
        "caption_override_accuracy": {
            **GATE_METRIC_REQUIREMENTS["caption_override_accuracy"],
            "override_mismatch_count": 0,
            "future_word_visible_frames": 0,
        },
        "factual_bindings": {
            **GATE_METRIC_REQUIREMENTS["factual_bindings"],
            "rendered_fact_mismatch_count": 0,
        },
        "readable_screen_context": {
            **GATE_METRIC_REQUIREMENTS["readable_screen_context"],
            "cropped_critical_region_count": 0,
        },
        "talking_head_geometry": {
            **GATE_METRIC_REQUIREMENTS["talking_head_geometry"],
            "clipped_face_frame_count": 0,
        },
        "long_routes_shared_body": {
            **GATE_METRIC_REQUIREMENTS["long_routes_shared_body"],
            "shared_body_hash_count": 1,
            "long_route_count_min": 3,
            "long_route_count_max": 6,
        },
    }
)

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

    if not isinstance(value, dict) or value.get("schema_version") not in {
        "eddy-professional-gates-v1",
        "professional-gate-evidence-v2",
    }:
        raise ValueError("professional_gates_schema_invalid")
    schema_version = str(value["schema_version"])
    required_gates = (
        REQUIRED_PROFESSIONAL_GATES_V2
        if schema_version == "professional-gate-evidence-v2"
        else REQUIRED_PROFESSIONAL_GATES
    )
    gates = value.get("gates")
    if not isinstance(gates, dict) or set(gates) != required_gates:
        raise ValueError("professional_gates_set_invalid")
    result: dict[str, bool] = {}
    evidence_refs: dict[str, str] = {}
    for gate_id in sorted(required_gates):
        row = gates[gate_id]
        if not isinstance(row, dict) or row.get("passed") is not True:
            raise ValueError(f"professional_gate_failed:{gate_id}")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"professional_gate_evidence_required:{gate_id}")
        for item in evidence:
            if schema_version == "professional-gate-evidence-v2":
                ref = validate_gate_evidence_v2(attempt, item, gate_id)
                prior_gate = evidence_refs.get(ref)
                if prior_gate is not None and prior_gate != gate_id:
                    raise ValueError(
                        f"professional_gate_evidence_reused_across_gates:{prior_gate}:{gate_id}"
                    )
                evidence_refs[ref] = gate_id
            else:
                _validate_evidence(attempt, item, gate_id)
        result[gate_id] = True
    return result


def validate_verifier_review(attempt: Path, value: object) -> dict[str, Any]:
    """Validate a no-edit verifier's complete watch/listen coverage."""

    if not isinstance(value, dict) or value.get("schema_version") not in {
        "verifier-review-v1",
        "verifier-review-v2",
    }:
        raise ValueError("verifier_review_schema_invalid")
    schema_version = str(value["schema_version"])
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
    long_count = len([ref for ref in reviewed_refs if ref.startswith("long-")])
    if (
        schema_version == "verifier-review-v1" and long_count != 3
    ) or (
        schema_version == "verifier-review-v2" and not 3 <= long_count <= 6
    ):
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
    if schema_version == "verifier-review-v2":
        _validate_boundary_review(attempt, value.get("boundary_review"))
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


def validate_gate_evidence_v2(attempt: Path, value: object, gate_id: str) -> str:
    if not isinstance(value, dict) or value.get("type") != "measurement":
        raise ValueError(f"professional_gate_evidence_v2_invalid:{gate_id}")
    ref = value.get("ref")
    if not isinstance(ref, str) or not ref.endswith(".json") or "#" in ref:
        raise ValueError(f"professional_gate_evidence_ref_invalid:{gate_id}")
    path_ref = Path(ref)
    if path_ref.is_absolute() or ".." in path_ref.parts:
        raise ValueError(f"professional_gate_evidence_ref_invalid:{gate_id}")
    path = attempt / path_ref
    if not path.is_file() or value.get("sha256") != _sha256(path):
        raise ValueError(f"professional_gate_evidence_hash_mismatch:{gate_id}")
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"professional_gate_evidence_payload_invalid:{gate_id}") from exc
    evaluator_id = GATE_EVALUATORS[gate_id]
    metrics = payload.get("metrics") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "professional-gate-evidence-v2"
        or payload.get("gate_id") != gate_id
        or payload.get("evaluator_id") != evaluator_id
        or payload.get("status") != "pass"
        or payload.get("self_attested") is not False
        or not isinstance(metrics, dict)
    ):
        raise ValueError(f"professional_gate_evidence_payload_invalid:{gate_id}")
    _validate_gate_metrics(gate_id, metrics)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError(f"professional_gate_evidence_artifacts_required:{gate_id}")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError(f"professional_gate_evidence_artifact_invalid:{gate_id}")
        artifact_ref = artifact.get("ref")
        if not isinstance(artifact_ref, str) or not artifact_ref.strip():
            raise ValueError(f"professional_gate_evidence_artifact_invalid:{gate_id}")
        artifact_path_ref = Path(artifact_ref)
        if artifact_path_ref.is_absolute() or ".." in artifact_path_ref.parts:
            raise ValueError(f"professional_gate_evidence_artifact_invalid:{gate_id}")
        artifact_path = attempt / artifact_path_ref
        if (
            not artifact_path.is_file()
            or artifact.get("sha256") != _sha256(artifact_path)
            or not isinstance(artifact.get("role"), str)
            or not artifact["role"].strip()
        ):
            raise ValueError(f"professional_gate_evidence_artifact_invalid:{gate_id}")
    return ref


def _validate_gate_metrics(gate_id: str, metrics: dict[str, Any]) -> None:
    required = GATE_METRIC_REQUIREMENTS[gate_id]
    if metrics.get("evaluated_by") != required["evaluated_by"]:
        raise ValueError(f"professional_gate_metrics_invalid:{gate_id}")
    sample_count = metrics.get("sample_count")
    if (
        not isinstance(sample_count, int)
        or isinstance(sample_count, bool)
        or sample_count < int(required["sample_count_min"])
        or metrics.get("failures") != 0
    ):
        raise ValueError(f"professional_gate_metrics_invalid:{gate_id}")
    for key, expected in required.items():
        if key in {"evaluated_by", "sample_count_min", "failures"}:
            continue
        if key == "long_route_count_min":
            if not isinstance(metrics.get("long_route_count"), int) or metrics[
                "long_route_count"
            ] < int(expected):
                raise ValueError(f"professional_gate_metrics_invalid:{gate_id}")
            continue
        if key == "long_route_count_max":
            if not isinstance(metrics.get("long_route_count"), int) or metrics[
                "long_route_count"
            ] > int(expected):
                raise ValueError(f"professional_gate_metrics_invalid:{gate_id}")
            continue
        if metrics.get(key) != expected:
            raise ValueError(f"professional_gate_metrics_invalid:{gate_id}")


def _validate_boundary_review(attempt: Path, value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("verifier_boundary_review_required")
    if (
        value.get("all_boundaries_reviewed") is not True
        or value.get("playback_speed") != 0.25
        or value.get("frame_window_each_side") != 8
        or value.get("decoder_policy") != "fps_mode_passthrough"
    ):
        raise ValueError("verifier_boundary_review_contract_invalid")
    for prefix in ("supercut", "candidate_decisions"):
        ref = value.get(f"{prefix}_ref")
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError(f"verifier_boundary_{prefix}_ref_invalid")
        path_ref = Path(ref)
        if path_ref.is_absolute() or ".." in path_ref.parts:
            raise ValueError(f"verifier_boundary_{prefix}_ref_invalid")
        path = attempt / path_ref
        if not path.is_file() or value.get(f"{prefix}_sha256") != _sha256(path):
            raise ValueError(f"verifier_boundary_{prefix}_hash_mismatch")
    decisions = json.loads((attempt / str(value["candidate_decisions_ref"])).read_text())
    if (
        not isinstance(decisions, dict)
        or decisions.get("schema_version") != "eddy-cut-boundary-audit-v1"
        or decisions.get("pass") is not True
        or decisions.get("unresolved") != []
        or decisions.get("drop_segment_ids") != []
    ):
        raise ValueError("verifier_boundary_candidates_unresolved")


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
