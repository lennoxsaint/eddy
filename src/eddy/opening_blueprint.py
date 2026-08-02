"""Validation for V7 Opening Edit Blueprint delivery and deviation receipts."""

from __future__ import annotations

import math
from typing import Any, Iterable


class OpeningBlueprintValidationError(ValueError):
    """The plan does not faithfully bind or deliver the pre-production blueprint."""


THRESHOLD_BASELINE = {
    "money_shot_by_second": 3,
    "real_proof_by_second": 10,
    "stakes_by_second": 30,
    "meaningful_visual_beats_min": 8,
    "meaningful_visual_beats_soft_max": 12,
}
PLANNED_JOB_FIELDS = (
    "semantic_job",
    "spoken_anchor",
    "asset_job",
    "proof_job",
    "audio_job",
    "motion_job",
    "cut_job",
    "intended_viewer_state",
    "fallback",
)


def _text(value: object, error: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpeningBlueprintValidationError(error)
    return value.strip()


def _hash(value: object, error: str) -> str:
    text = _text(value, error)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text.lower()):
        raise OpeningBlueprintValidationError(error)
    return text


def _text_list(value: object, error: str, *, minimum: int = 1) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) < minimum
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise OpeningBlueprintValidationError(error)
    normalized = [str(item).strip() for item in value]
    if len(set(normalized)) != len(normalized):
        raise OpeningBlueprintValidationError(error)
    return normalized


def _planned_scene(
    value: object,
    *,
    hook_id: str,
    maximum_second: float,
) -> str:
    if not isinstance(value, dict):
        raise OpeningBlueprintValidationError(
            f"opening_blueprint_planned_scene_invalid:{hook_id}"
        )
    beat_id = _text(
        value.get("beat_id"),
        f"opening_blueprint_planned_scene_id_required:{hook_id}",
    )
    start = value.get("start_second")
    end = value.get("end_second")
    if (
        isinstance(start, bool)
        or not isinstance(start, (int, float))
        or isinstance(end, bool)
        or not isinstance(end, (int, float))
        or not math.isfinite(float(start))
        or not math.isfinite(float(end))
        or float(start) < 0
        or float(end) <= float(start)
        or float(end) > maximum_second
    ):
        raise OpeningBlueprintValidationError(
            f"opening_blueprint_planned_scene_range_invalid:{beat_id}"
        )
    _text_list(
        value.get("mechanic_ids"),
        f"opening_blueprint_planned_scene_mechanics_required:{beat_id}",
    )
    for field in PLANNED_JOB_FIELDS:
        _text(
            value.get(field),
            f"opening_blueprint_planned_scene_{field}_required:{beat_id}",
        )
    return beat_id


def _benchmark_binding(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OpeningBlueprintValidationError("opening_blueprint_benchmark_binding_required")
    _text(value.get("benchmark_revision"), "opening_blueprint_benchmark_revision_required")
    _text(value.get("mechanics_library_id"), "opening_blueprint_mechanics_library_id_required")
    _text(value.get("mechanics_library_ref"), "opening_blueprint_mechanics_library_ref_required")
    _hash(value.get("mechanics_library_sha256"), "opening_blueprint_mechanics_library_hash_invalid")
    if value.get("evidence_authority") != "observed_cross_creator_not_causal":
        raise OpeningBlueprintValidationError("opening_blueprint_evidence_authority_invalid")
    return dict(value)


def validate_opening_blueprint_contract(
    value: object,
    *,
    hook_ids: Iterable[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OpeningBlueprintValidationError("opening_visual_contract_required")
    if value.get("schema_version") != "2.0" or value.get("profile_version") != 7:
        raise OpeningBlueprintValidationError("opening_blueprint_contract_version_invalid")
    if value.get("contract_kind") != "opening_edit_blueprint":
        raise OpeningBlueprintValidationError("opening_blueprint_contract_kind_invalid")
    if value.get("delivery_target_schema") != "edit-plan-v3.6":
        raise OpeningBlueprintValidationError(
            "opening_blueprint_delivery_target_schema_invalid"
        )
    _text(value.get("contract_ref"), "opening_blueprint_contract_ref_required")
    _hash(value.get("contract_sha256"), "opening_blueprint_contract_hash_invalid")
    contact_sheet_ref = value.get("opening_contact_sheet_ref") or value.get(
        "contact_sheet_ref"
    )
    _text(contact_sheet_ref, "opening_blueprint_contact_sheet_ref_required")
    binding = _benchmark_binding(value.get("benchmark_binding"))
    global_mechanics = set(
        _text_list(
            binding.get("selected_mechanic_ids"),
            "opening_blueprint_selected_mechanics_required",
        )
    )

    expected_hooks = tuple(hook_ids)
    variants = value.get("variants")
    if not isinstance(variants, list) or len(variants) != 3:
        raise OpeningBlueprintValidationError("three_opening_blueprint_variants_required")
    actual_hooks: list[str] = []
    variant_ids: list[str] = []
    for variant in variants:
        if not isinstance(variant, dict):
            raise OpeningBlueprintValidationError("opening_blueprint_variant_invalid")
        variant_ids.append(_text(variant.get("variant_id"), "opening_blueprint_variant_id_required"))
        hook_id = _text(variant.get("hook_id"), "opening_blueprint_hook_id_required")
        actual_hooks.append(hook_id)
        if variant.get("style_policy") != "function_locked_style_flexible":
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_style_policy_invalid:{hook_id}"
            )
        blueprint = variant.get("opening_edit_blueprint")
        if isinstance(blueprint, dict):
            if blueprint.get("window_seconds") != [0, 30]:
                raise OpeningBlueprintValidationError(
                    f"opening_blueprint_window_invalid:{hook_id}"
                )
            beats = blueprint.get("beats")
            if not isinstance(beats, list):
                raise OpeningBlueprintValidationError(
                    f"opening_blueprint_eight_to_twelve_beats_required:{hook_id}"
                )
            opening_ids = _text_list(
                [
                    _planned_scene(beat, hook_id=hook_id, maximum_second=30)
                    for beat in beats
                ],
                f"opening_blueprint_eight_to_twelve_beats_required:{hook_id}",
                minimum=8,
            )
            if min(float(beat["start_second"]) for beat in beats) > 0.04:
                raise OpeningBlueprintValidationError(
                    f"opening_blueprint_frame_one_activity_required:{hook_id}"
                )
        else:
            opening_ids = _text_list(
                variant.get("blueprint_beat_ids"),
                f"opening_blueprint_eight_to_twelve_beats_required:{hook_id}",
                minimum=8,
            )
        if len(opening_ids) > 12:
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_eight_to_twelve_beats_required:{hook_id}"
            )
        bridge = variant.get("bridge_30_60")
        if isinstance(bridge, dict):
            if bridge.get("window_seconds") != [30, 60]:
                raise OpeningBlueprintValidationError(
                    f"opening_blueprint_bridge_window_invalid:{hook_id}"
                )
            scenes = bridge.get("scenes")
            if not isinstance(scenes, list):
                raise OpeningBlueprintValidationError(
                    f"opening_blueprint_bridge_scene_ids_required:{hook_id}"
                )
            bridge_ids = _text_list(
                [
                    _planned_scene(scene, hook_id=hook_id, maximum_second=60)
                    for scene in scenes
                ],
                f"opening_blueprint_bridge_scene_ids_required:{hook_id}",
            )
            if (
                min(float(scene["start_second"]) for scene in scenes) > 30.04
                or max(float(scene["end_second"]) for scene in scenes) < 60
                or any(float(scene["start_second"]) < 30 for scene in scenes)
            ):
                raise OpeningBlueprintValidationError(
                    f"opening_blueprint_bridge_coverage_invalid:{hook_id}"
                )
        else:
            bridge_ids = _text_list(
                variant.get("bridge_scene_ids"),
                f"opening_blueprint_bridge_scene_ids_required:{hook_id}",
            )
        if set(opening_ids) & set(bridge_ids):
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_scene_ids_must_be_unique:{hook_id}"
            )
        variant_mechanics = variant.get("selected_mechanic_ids")
        if variant_mechanics is None and isinstance(blueprint, dict):
            scene_rows: list[object] = []
            raw_beats = blueprint.get("beats")
            if isinstance(raw_beats, list):
                scene_rows.extend(raw_beats)
            raw_scenes = bridge.get("scenes") if isinstance(bridge, dict) else None
            if isinstance(raw_scenes, list):
                scene_rows.extend(raw_scenes)
            variant_mechanics = sorted(
                {
                    str(mechanic_id)
                    for scene in scene_rows
                    if isinstance(scene, dict)
                    for mechanic_id in scene.get("mechanic_ids", [])
                    if isinstance(mechanic_id, str) and mechanic_id.strip()
                }
            )
        mechanics = set(
            _text_list(
                variant_mechanics,
                f"opening_blueprint_selected_mechanics_required:{hook_id}",
            )
        )
        if not mechanics <= global_mechanics:
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_mechanic_not_in_benchmark_binding:{hook_id}"
            )
        if variant.get("thresholds") != THRESHOLD_BASELINE:
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_threshold_version_drift:{hook_id}"
            )
        review_fields = (
            ("muted_preview_status", "muted_preview"),
            ("mobile_preview_status", "mobile_preview"),
            ("taste_review_status", "taste_review"),
        )
        for status_field, object_field in review_fields:
            review_value = variant.get(status_field)
            if review_value is None and isinstance(variant.get(object_field), dict):
                review_value = variant[object_field].get("status")
            if review_value != "pass":
                raise OpeningBlueprintValidationError(
                    f"opening_blueprint_{status_field}_must_pass:{hook_id}"
                )
    if tuple(actual_hooks) != expected_hooks:
        raise OpeningBlueprintValidationError("opening_blueprint_hooks_must_match_ranked_hooks")
    if len(set(variant_ids)) != 3:
        raise OpeningBlueprintValidationError("opening_blueprint_variant_ids_must_be_unique")
    return dict(value)


def planned_variant_ids(variant: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return planned opening and bridge IDs from either the full or compact contract."""
    blueprint = variant.get("opening_edit_blueprint")
    bridge = variant.get("bridge_30_60")
    if isinstance(blueprint, dict) and isinstance(bridge, dict):
        opening_ids = [
            str(beat["beat_id"])
            for beat in blueprint.get("beats", [])
            if isinstance(beat, dict) and isinstance(beat.get("beat_id"), str)
        ]
        bridge_ids = [
            str(scene["beat_id"])
            for scene in bridge.get("scenes", [])
            if isinstance(scene, dict) and isinstance(scene.get("beat_id"), str)
        ]
        return opening_ids, bridge_ids
    return (
        [str(value) for value in variant.get("blueprint_beat_ids", [])],
        [str(value) for value in variant.get("bridge_scene_ids", [])],
    )


def planned_variant_mechanics(variant: dict[str, Any]) -> set[str]:
    """Return the mechanics available to one opening variant."""
    explicit = variant.get("selected_mechanic_ids")
    if isinstance(explicit, list):
        return {str(value) for value in explicit}
    blueprint = variant.get("opening_edit_blueprint")
    bridge = variant.get("bridge_30_60")
    scenes = [
        *(blueprint.get("beats", []) if isinstance(blueprint, dict) else []),
        *(bridge.get("scenes", []) if isinstance(bridge, dict) else []),
    ]
    return {
        str(mechanic_id)
        for scene in scenes
        if isinstance(scene, dict)
        for mechanic_id in scene.get("mechanic_ids", [])
        if isinstance(mechanic_id, str)
    }


def _validate_deviation(mapping: dict[str, Any], *, scene_id: str) -> None:
    jobs_match = mapping.get("jobs_match")
    deviation = mapping.get("deviation")
    if jobs_match is True:
        if deviation is not None and deviation != {}:
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_unnecessary_deviation_receipt:{scene_id}"
            )
        return
    if jobs_match is not False or not isinstance(deviation, dict):
        raise OpeningBlueprintValidationError(
            f"opening_blueprint_deviation_receipt_required:{scene_id}"
        )
    for field in (
        "deviation_id",
        "reason",
        "planned_job",
        "delivered_job",
        "viewer_impact",
        "receipt_ref",
    ):
        _text(
            deviation.get(field),
            f"opening_blueprint_deviation_{field}_required:{scene_id}",
        )
    if deviation.get("status") != "review_required":
        raise OpeningBlueprintValidationError(
            f"opening_blueprint_deviation_status_invalid:{scene_id}"
        )
    _hash(
        deviation.get("receipt_sha256"),
        f"opening_blueprint_deviation_receipt_hash_invalid:{scene_id}",
    )


def validate_opening_blueprint_delivery(
    value: object,
    *,
    contract: dict[str, Any],
    visual_choreography: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OpeningBlueprintValidationError("opening_blueprint_delivery_required")
    if value.get("schema_version") != "eddy-opening-blueprint-delivery-v1":
        raise OpeningBlueprintValidationError("opening_blueprint_delivery_schema_invalid")
    if value.get("contract_sha256") != contract.get("contract_sha256"):
        raise OpeningBlueprintValidationError("opening_blueprint_delivery_contract_hash_mismatch")
    if value.get("benchmark_binding") != contract.get("benchmark_binding"):
        raise OpeningBlueprintValidationError("opening_blueprint_delivery_benchmark_mismatch")

    contract_by_hook = {
        str(variant["hook_id"]): variant for variant in contract["variants"]
    }
    choreography_by_hook = {
        str(opening["hook_id"]): opening
        for opening in visual_choreography.get("openings", [])
        if isinstance(opening, dict)
    }
    openings = value.get("openings")
    if not isinstance(openings, list) or len(openings) != 3:
        raise OpeningBlueprintValidationError(
            "three_opening_blueprint_deliveries_required"
        )
    delivered_hooks: list[str] = []
    for delivery in openings:
        if not isinstance(delivery, dict):
            raise OpeningBlueprintValidationError("opening_blueprint_delivery_invalid")
        hook_id = _text(delivery.get("hook_id"), "opening_blueprint_delivery_hook_required")
        delivered_hooks.append(hook_id)
        variant = contract_by_hook.get(hook_id)
        choreography = choreography_by_hook.get(hook_id)
        if variant is None or choreography is None:
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_delivery_hook_unknown:{hook_id}"
            )
        if delivery.get("variant_id") != variant.get("variant_id"):
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_delivery_variant_mismatch:{hook_id}"
            )
        scenes = [
            scene
            for scene in choreography.get("scenes", [])
            if isinstance(scene, dict) and float(scene.get("start", math.inf)) < 60
        ]
        if not scenes:
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_delivery_scenes_required:{hook_id}"
            )
        if float(scenes[0]["start"]) > 0.04 or float(scenes[-1]["end"]) < 60:
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_delivery_must_cover_zero_to_sixty:{hook_id}"
            )
        mappings = delivery.get("scene_mappings")
        if not isinstance(mappings, list) or len(mappings) != len(scenes):
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_every_delivered_scene_requires_mapping:{hook_id}"
            )
        scene_ids = {str(scene["id"]) for scene in scenes}
        opening_ids, bridge_ids = planned_variant_ids(variant)
        planned_ids = set(opening_ids) | set(bridge_ids)
        planned_rows = {
            str(scene["beat_id"]): scene
            for block in (
                variant.get("opening_edit_blueprint"),
                variant.get("bridge_30_60"),
            )
            if isinstance(block, dict)
            for scene in (
                block.get("beats", [])
                if isinstance(block.get("beats"), list)
                else block.get("scenes", [])
            )
            if isinstance(scene, dict) and isinstance(scene.get("beat_id"), str)
        }
        mapped_scene_ids: list[str] = []
        mapped_blueprint_ids: list[str] = []
        allowed_mechanics = planned_variant_mechanics(variant)
        for mapping in mappings:
            if not isinstance(mapping, dict):
                raise OpeningBlueprintValidationError(
                    f"opening_blueprint_scene_mapping_invalid:{hook_id}"
                )
            scene_id = _text(
                mapping.get("delivered_scene_id"),
                f"opening_blueprint_delivered_scene_id_required:{hook_id}",
            )
            blueprint_id = _text(
                mapping.get("blueprint_beat_id"),
                f"opening_blueprint_beat_id_required:{scene_id}",
            )
            mapped_scene_ids.append(scene_id)
            mapped_blueprint_ids.append(blueprint_id)
            mechanics = set(
                _text_list(
                    mapping.get("mechanic_ids"),
                    f"opening_blueprint_mapping_mechanics_required:{scene_id}",
                )
            )
            if not mechanics <= allowed_mechanics:
                raise OpeningBlueprintValidationError(
                    f"opening_blueprint_mapping_mechanic_unknown:{scene_id}"
                )
            for field in PLANNED_JOB_FIELDS:
                _text(
                    mapping.get(field),
                    f"opening_blueprint_mapping_{field}_required:{scene_id}",
                )
            planned = planned_rows.get(blueprint_id)
            if planned is not None:
                jobs_match = all(
                    mapping.get(field) == planned.get(field)
                    for field in PLANNED_JOB_FIELDS
                )
                if mapping.get("jobs_match") is not jobs_match:
                    raise OpeningBlueprintValidationError(
                        f"opening_blueprint_jobs_match_claim_invalid:{scene_id}"
                    )
            _validate_deviation(mapping, scene_id=scene_id)
        if set(mapped_scene_ids) != scene_ids or len(set(mapped_scene_ids)) != len(
            mapped_scene_ids
        ):
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_delivered_scene_mapping_mismatch:{hook_id}"
            )
        if set(mapped_blueprint_ids) != planned_ids or len(set(mapped_blueprint_ids)) != len(
            mapped_blueprint_ids
        ):
            raise OpeningBlueprintValidationError(
                f"opening_blueprint_planned_scene_mapping_mismatch:{hook_id}"
            )
    if tuple(delivered_hooks) != tuple(contract_by_hook):
        raise OpeningBlueprintValidationError(
            "opening_blueprint_delivery_hooks_must_match_contract"
        )
    return dict(value)
