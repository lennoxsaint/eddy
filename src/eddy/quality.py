"""Versioned quality profiles and v3.4 production-contract validation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


GENERIC_PROFILE_ID = "creator_good_v1"
LENNOX_PROFILE_ID = "lennox-professional-youtube-v1"
PROFILE_FILES = {
    GENERIC_PROFILE_ID: "references/creator-good-v1.json",
    LENNOX_PROFILE_ID: "references/owner-profiles/lennox-professional-youtube-v1.json",
}


class QualityContractError(ValueError):
    """A quality profile or v3.4 production contract is invalid."""


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
    if not isinstance(value, dict) or value.get("schema_version") != "eddy-audio-plan-v1":
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
    if not isinstance(value, dict) or value.get("schema_version") != "eddy-caption-policy-v1":
        raise QualityContractError("caption_policy_schema_invalid")
    required = {
        "prior_words": "visible",
        "active_word": "highlighted",
        "future_words": "invisible",
        "source_caption_collision": "suppress_eddy_captions",
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise QualityContractError("caption_policy_progressive_contract_invalid")
    intervals = value.get("source_caption_intervals", {})
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
    return dict(value)


def validate_production_review(value: object) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "eddy-production-review-v1"
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
    return dict(value)


def _valid_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )
