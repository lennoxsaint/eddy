"""Versioned quality profiles and production-contract validation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


GENERIC_PROFILE_ID = "creator_good_v1"
LENNOX_PROFILE_ID = "lennox-professional-youtube-v3"
LENNOX_PROFILE_V2_ID = "lennox-professional-youtube-v2"
LENNOX_PROFILE_V1_ID = "lennox-professional-youtube-v1"
PROFILE_FILES = {
    GENERIC_PROFILE_ID: "references/creator-good-v1.json",
    LENNOX_PROFILE_V1_ID: "references/owner-profiles/lennox-professional-youtube-v1.json",
    LENNOX_PROFILE_V2_ID: "references/owner-profiles/lennox-professional-youtube-v2.json",
    LENNOX_PROFILE_ID: "references/owner-profiles/lennox-professional-youtube-v3.json",
}


class QualityContractError(ValueError):
    """A quality profile or versioned production contract is invalid."""


def resolve_quality_profile(
    canonical_root: Path,
    *,
    explicit_profile_id: str | None = None,
    owner_state_path: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Resolve explicit selection, then owner-channel selection, then generic."""

    profile_id = explicit_profile_id
    state_path = owner_state_path or Path.home() / ".eddy" / "owner-channel.json"
    if profile_id is None and state_path.is_file():
        try:
            owner_state = json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            owner_state = {}
        selected = owner_state.get("profile_id")
        if isinstance(selected, str) and selected.strip():
            profile_id = selected.strip()
    profile_id = profile_id or GENERIC_PROFILE_ID
    relative = PROFILE_FILES.get(profile_id)
    if relative is None:
        raise QualityContractError(f"quality_profile_unknown:{profile_id}")
    path = canonical_root / relative
    if not path.is_file():
        raise QualityContractError(f"quality_profile_missing:{profile_id}")
    profile = json.loads(path.read_text())
    if profile.get("id") != profile_id:
        raise QualityContractError(f"quality_profile_id_mismatch:{profile_id}")
    if profile.get("schema_version") not in {
        "eddy-quality-profile-v1",
        "eddy-quality-profile-v2",
        "eddy-quality-profile-v3",
        "eddy-quality-profile-v4",
    }:
        raise QualityContractError(f"quality_profile_schema_invalid:{profile_id}")
    return profile, path


def validate_contract_ref(value: object, *, schema: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QualityContractError(f"{label}_required")
    if value.get("schema_version") != schema:
        raise QualityContractError(f"{label}_schema_invalid")
    ref = value.get("ref")
    if (
        not isinstance(ref, str)
        or not ref.strip()
        or Path(ref).is_absolute()
        or ".." in Path(ref).parts
    ):
        raise QualityContractError(f"{label}_ref_invalid")
    if not _valid_hash(value.get("sha256")):
        raise QualityContractError(f"{label}_sha256_invalid")
    return dict(value)


def validate_audio_plan(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") not in {
        "eddy-audio-plan-v1",
        "eddy-audio-plan-v2",
    }:
        raise QualityContractError("audio_plan_schema_invalid")
    music = value.get("music")
    sfx = value.get("sfx")
    if not isinstance(music, list) or not music:
        raise QualityContractError("audio_plan_music_required")
    if not isinstance(sfx, list) or not sfx:
        raise QualityContractError("audio_plan_sfx_required")
    for row in [*music, *sfx]:
        if not isinstance(row, dict):
            raise QualityContractError("audio_plan_cue_invalid")
        for key in ("ref", "provenance", "license", "cue", "purpose", "mix_db"):
            if row.get(key) in {None, ""}:
                raise QualityContractError(f"audio_plan_cue_{key}_required")
        if (
            not isinstance(row["mix_db"], (int, float))
            or not math.isfinite(float(row["mix_db"]))
            or not -60 <= float(row["mix_db"]) <= 0
        ):
            raise QualityContractError("audio_plan_cue_mix_db_invalid")
        ref = Path(str(row["ref"]))
        if ref.is_absolute() or ".." in ref.parts:
            raise QualityContractError("audio_plan_cue_ref_invalid")
    if value.get("paid_retrieval_allowed") is not False:
        raise QualityContractError("audio_plan_paid_retrieval_must_be_false")
    if value["schema_version"] == "eddy-audio-plan-v2":
        if value.get("studio_sound_required") is not True:
            raise QualityContractError("audio_plan_studio_sound_required")
        if value.get("studio_sound_lineage_policy") != "verified_descript_only":
            raise QualityContractError("audio_plan_studio_sound_lineage_invalid")
        if value.get("shorts_music_policy") != "purposeful_variation":
            raise QualityContractError("audio_plan_shorts_music_policy_invalid")
    return dict(value)


def validate_grade_plan(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != "eddy-grade-plan-v1":
        raise QualityContractError("grade_plan_schema_invalid")
    if value.get("camera_goal") != "natural_skin_exposure_white_balance_consistency":
        raise QualityContractError("grade_plan_camera_goal_invalid")
    if value.get("screen_recording_policy") != "preserve_source_color_fidelity":
        raise QualityContractError("grade_plan_screen_policy_invalid")
    if not isinstance(value.get("shot_checks"), list) or not value["shot_checks"]:
        raise QualityContractError("grade_plan_shot_checks_required")
    return dict(value)


def validate_caption_policy(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") not in {
        "eddy-caption-policy-v1",
        "eddy-caption-policy-v2",
    }:
        raise QualityContractError("caption_policy_schema_invalid")
    if value["schema_version"] == "eddy-caption-policy-v2":
        longs = value.get("longs")
        shorts = value.get("shorts")
        if (
            not isinstance(longs, dict)
            or not isinstance(longs.get("designed_captions"), bool)
            or longs.get("default") != "disabled"
        ):
            raise QualityContractError("caption_policy_longs_invalid")
        required = {
            "prior_words": "visible",
            "active_word": "highlighted",
            "future_words": "invisible",
            "source_caption_collision": "suppress_eddy_captions",
            "speaker_attribution": "color_plus_label",
            "speaker_colors": "design_contract_accessible_palette",
        }
        if not isinstance(shorts, dict) or any(
            shorts.get(key) != expected for key, expected in required.items()
        ):
            raise QualityContractError("caption_policy_shorts_invalid")
        _validate_source_caption_intervals(shorts.get("source_caption_intervals", {}))
        return dict(value)
    required = {
        "prior_words": "visible",
        "active_word": "highlighted",
        "future_words": "invisible",
        "source_caption_collision": "suppress_eddy_captions",
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise QualityContractError("caption_policy_progressive_contract_invalid")
    _validate_source_caption_intervals(value.get("source_caption_intervals", {}))
    return dict(value)


def _validate_source_caption_intervals(intervals: object) -> None:
    if not isinstance(intervals, dict):
        raise QualityContractError("caption_policy_source_intervals_invalid")
    for short_id, ranges in intervals.items():
        if not isinstance(short_id, str) or not isinstance(ranges, list):
            raise QualityContractError("caption_policy_source_intervals_invalid")
        for row in ranges:
            if (
                not isinstance(row, list)
                or len(row) != 2
                or not all(isinstance(item, (int, float)) for item in row)
            or float(row[0]) < 0
            or float(row[1]) <= float(row[0])
        ):
                raise QualityContractError("caption_policy_source_interval_invalid")


def validate_production_review(value: object) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.get("schema_version")
        not in {"eddy-production-review-v1", "eddy-production-review-v2"}
    ):
        raise QualityContractError("production_review_schema_invalid")
    if value.get("minimum_complete_passes") != 3:
        raise QualityContractError("production_review_three_passes_required")
    if value.get("target_score") != 100 or value.get("maximum_score") != 100:
        raise QualityContractError("production_review_score_must_be_100")
    if value.get("audience_performance") != "NOT_RUN":
        raise QualityContractError("audience_performance_must_be_not_run")
    if value.get("final_authority") != "owner_taste_lock":
        raise QualityContractError("production_review_owner_lock_required")
    if value.get("repair_policy") != "change_strategy_until_green_or_exact_blocker":
        raise QualityContractError("production_review_repair_policy_invalid")
    strategy_id = value.get("strategy_id")
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise QualityContractError("production_review_strategy_id_required")
    if value["schema_version"] == "eddy-production-review-v2":
        if value.get("verifier_authority") != "independent_no_edit_context":
            raise QualityContractError("production_review_verifier_authority_invalid")
        if value.get("verifier_edit_authority") is not False:
            raise QualityContractError("production_review_verifier_must_not_edit")
        if (
            value.get("repair_review_policy")
            != "repaired_intervals_and_joins_plus_full_final"
        ):
            raise QualityContractError("production_review_rewatch_policy_invalid")
        if value.get("promotion_state") != (
            "proof_gated_candidate_awaiting_owner_taste"
        ):
            raise QualityContractError("production_review_promotion_state_invalid")
        if value.get("open_items_policy") != "objective_closed_subjective_optional":
            raise QualityContractError("production_review_open_items_policy_invalid")
    return dict(value)


def validate_cut_integrity_plan(value: object) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.get("schema_version")
        not in {"eddy-cut-integrity-plan-v1", "eddy-cut-integrity-plan-v2"}
    ):
        raise QualityContractError("cut_integrity_plan_schema_invalid")
    required = {
        "timing_authority": "waveform_energy_envelope_when_transcript_conflicts",
        "sample_exact_splices": True,
        "sequence_search_parity": True,
        "word_edge_protection": True,
        "delivered_retranscription": True,
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise QualityContractError("cut_integrity_plan_contract_invalid")
    latency = value.get("shot_entry_latency_max_frames")
    if not isinstance(latency, int) or isinstance(latency, bool) or not 0 <= latency <= 2:
        raise QualityContractError("cut_integrity_shot_latency_invalid")
    exceptions = value.get("protected_exception_ids")
    if not isinstance(exceptions, list) or not all(
        isinstance(item, str) and item.strip() for item in exceptions
    ):
        raise QualityContractError("cut_integrity_exceptions_invalid")
    if value["schema_version"] == "eddy-cut-integrity-plan-v2":
        v2_required = {
            "boundary_manifest_required": True,
            "micro_insert_frames": [1, 6],
            "silent_handle_max_seconds": 0.24,
            "silent_handle_max_dbfs": -40,
            "boundary_frame_window_each_side": 8,
            "boundary_supercut_speed": 0.25,
            "decoder_policy": "fps_mode_passthrough",
            "protected_exception_evidence_required": True,
            "complete_clause_source_check_required": True,
        }
        if any(value.get(key) != expected for key, expected in v2_required.items()):
            raise QualityContractError("cut_integrity_plan_v2_contract_invalid")
    return dict(value)


def validate_proof_plan(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != "eddy-proof-plan-v1":
        raise QualityContractError("proof_plan_schema_invalid")
    if value.get("real_capture_preferred") is not True:
        raise QualityContractError("proof_plan_real_capture_preference_required")
    if value.get("reconstruction_receipt_required") is not True:
        raise QualityContractError("proof_plan_reconstruction_receipt_required")
    claims = value.get("claims")
    if not isinstance(claims, list):
        raise QualityContractError("proof_plan_claims_invalid")
    for row in claims:
        if not isinstance(row, dict):
            raise QualityContractError("proof_plan_claim_invalid")
        if row.get("evidence_kind") not in {"capture", "reconstructed"}:
            raise QualityContractError("proof_plan_evidence_kind_invalid")
        if not isinstance(row.get("claim_id"), str) or not row["claim_id"].strip():
            raise QualityContractError("proof_plan_claim_id_required")
        for key in ("source_refs", "factual_bindings"):
            values = row.get(key)
            if not isinstance(values, list) or not all(
                isinstance(item, str) and item.strip() for item in values
            ):
                raise QualityContractError(f"proof_plan_{key}_invalid")
        if row["evidence_kind"] == "reconstructed" and (
            not row["source_refs"] or not row["factual_bindings"]
        ):
            raise QualityContractError("proof_plan_reconstruction_unbound")
    annotations = value.get("annotation_targets")
    if not isinstance(annotations, list):
        raise QualityContractError("proof_plan_annotation_targets_invalid")
    return dict(value)


def _valid_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )
