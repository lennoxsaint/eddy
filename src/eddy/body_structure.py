"""Validation for the Sage-owned body spine consumed by Eddy v3.3."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any


class BodyStructureValidationError(ValueError):
    """The edit plan drifted from the locked pre-production body structure."""


BODY_MODES = {"countable_guide", "live_test", "proof_led_argument"}
PROGRESS_UNITS = {
    "countable_guide": {"step", "item", "capability", "mistake"},
    "live_test": {"round", "test", "decision"},
    "proof_led_argument": {"question", "claim", "turn"},
}
STORY_ROLES = {"none", "evidence", "stakes", "decision"}
PROOF_AUTHORITIES = {"raw_source", "supplied_asset", "pixel_faithful_demo"}


def validate_body_structure_contract(
    value: object,
    *,
    visual_choreography: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BodyStructureValidationError("body_structure_contract_required")
    if value.get("schema_version") != "eddy-body-structure-v1":
        raise BodyStructureValidationError("body_structure_contract_schema_invalid")
    _validate_source_ref(value.get("source_contract_ref"))
    if not _valid_hash(value.get("source_contract_sha256")):
        raise BodyStructureValidationError("body_structure_source_contract_sha256_invalid")
    if value.get("major_order_authority") != "sage_locked_eddy_may_not_reorder":
        raise BodyStructureValidationError("body_structure_major_order_authority_invalid")

    mode = value.get("mode")
    if not isinstance(mode, str) or mode not in BODY_MODES:
        raise BodyStructureValidationError("body_structure_mode_invalid")
    route = value.get("route_contract")
    if not isinstance(route, dict):
        raise BodyStructureValidationError("body_structure_route_contract_required")
    for field in ("proof", "promise", "plan"):
        _required_text(route.get(field), f"body_structure_route_{field}_required")
    understood = route.get("understood_by_second")
    if (
        not isinstance(understood, (int, float))
        or isinstance(understood, bool)
        or not math.isfinite(float(understood))
        or not 0 <= float(understood) <= 30
    ):
        raise BodyStructureValidationError("body_structure_route_must_be_understood_by_second_thirty")
    if route.get("progress_unit") not in tuple(PROGRESS_UNITS[mode]):
        raise BodyStructureValidationError("body_structure_progress_unit_invalid")

    sections = value.get("sections")
    if not isinstance(sections, list) or not 3 <= len(sections) <= 5:
        raise BodyStructureValidationError("body_structure_sections_must_be_3_to_5")
    if not all(isinstance(section, dict) for section in sections):
        raise BodyStructureValidationError("body_structure_section_invalid")
    section_ids = [str(section.get("section_id", "")).strip() for section in sections]
    if route.get("section_ids") != section_ids:
        raise BodyStructureValidationError("body_structure_section_order_mismatch")

    shared_body = visual_choreography.get("shared_body")
    scenes = shared_body.get("scenes") if isinstance(shared_body, dict) else None
    if not isinstance(scenes, list) or not all(isinstance(scene, dict) for scene in scenes):
        raise BodyStructureValidationError("body_structure_shared_body_scenes_required")
    scene_by_id = {str(scene.get("id")): scene for scene in scenes}
    visual_scene_ids = [str(scene.get("id")) for scene in scenes]

    mapped_scene_ids: list[str] = []
    for index, section in enumerate(sections):
        section_id = _required_text(section.get("section_id"), "body_structure_section_id_required")
        for field in ("label", "question", "payoff", "viewer_action"):
            _required_text(section.get(field), f"body_structure_section_{field}_required")
        scene_ids = section.get("scene_ids")
        if not isinstance(scene_ids, list) or not scene_ids or not all(_is_text(item) for item in scene_ids):
            raise BodyStructureValidationError("body_structure_section_scene_ids_required")
        mapped_scene_ids.extend(str(scene_id) for scene_id in scene_ids)
        proof_scene_ids = section.get("proof_scene_ids")
        if not isinstance(proof_scene_ids, list) or not proof_scene_ids:
            raise BodyStructureValidationError("body_structure_proof_scene_required")
        if not all(proof_scene_id in scene_ids for proof_scene_id in proof_scene_ids):
            raise BodyStructureValidationError("body_structure_proof_scene_outside_section")
        for proof_scene_id in proof_scene_ids:
            proof_scene = scene_by_id.get(str(proof_scene_id))
            if not isinstance(proof_scene, dict) or proof_scene.get("evidence_authority") not in PROOF_AUTHORITIES:
                raise BodyStructureValidationError("body_structure_proof_scene_authority_invalid")
        is_final = index == len(sections) - 1
        if not is_final:
            _required_text(section.get("next_loop"), "body_structure_next_loop_required")
        elif section.get("next_loop") not in (None, ""):
            raise BodyStructureValidationError("body_structure_final_next_loop_must_be_empty")
        story_role = section.get("story_role")
        if not isinstance(story_role, str) or story_role not in STORY_ROLES:
            raise BodyStructureValidationError("body_structure_story_role_invalid")
        if story_role == "none":
            if section.get("story_source_ref") not in (None, ""):
                raise BodyStructureValidationError("body_structure_story_source_ref_unexpected")
        else:
            _required_text(section.get("story_source_ref"), "body_structure_story_source_ref_required")
        for scene_id in scene_ids:
            scene = scene_by_id.get(str(scene_id))
            if not isinstance(scene, dict) or scene.get("body_section_id") != section_id:
                raise BodyStructureValidationError("body_structure_scene_section_binding_mismatch")

    if len(set(section_ids)) != len(section_ids):
        raise BodyStructureValidationError("body_structure_section_ids_must_be_unique")
    if mapped_scene_ids != visual_scene_ids or len(set(mapped_scene_ids)) != len(mapped_scene_ids):
        raise BodyStructureValidationError("body_structure_scene_coverage_mismatch")

    cues = value.get("progress_cues")
    expected_after_ids = section_ids[:-1]
    if not isinstance(cues, list) or len(cues) != len(expected_after_ids):
        raise BodyStructureValidationError("body_structure_progress_cues_mismatch")
    for index, cue in enumerate(cues):
        if not isinstance(cue, dict) or cue.get("after_section_id") != expected_after_ids[index]:
            raise BodyStructureValidationError("body_structure_progress_cues_mismatch")
        next_section = sections[index + 1]
        expected_scene_id = next_section["scene_ids"][0]
        if cue.get("scene_id") != expected_scene_id:
            raise BodyStructureValidationError("body_structure_progress_cue_scene_mismatch")
        cue_scene = scene_by_id.get(str(expected_scene_id))
        if not isinstance(cue_scene, dict) or cue_scene.get("semantic_job") != "reset":
            raise BodyStructureValidationError("body_structure_progress_cue_scene_must_be_reset")
        _required_text(cue.get("transition_card"), "body_structure_transition_card_required")
        _required_text(cue.get("spoken_callback"), "body_structure_spoken_callback_required")

    final_payoff = value.get("final_payoff")
    if not isinstance(final_payoff, dict):
        raise BodyStructureValidationError("body_structure_final_payoff_required")
    if final_payoff.get("section_id") != section_ids[-1]:
        raise BodyStructureValidationError("body_structure_final_payoff_section_mismatch")
    for field in ("verdict", "resulting_action", "earned_cta_relationship"):
        _required_text(final_payoff.get(field), f"body_structure_final_payoff_{field}_required")
    return dict(value)


def _validate_source_ref(value: object) -> None:
    if not _is_text(value):
        raise BodyStructureValidationError("body_structure_source_contract_ref_invalid")
    raw = str(value)
    path_text, separator, fragment = raw.partition("#")
    path = Path(path_text)
    if (
        separator != "#"
        or fragment != "body_structure"
        or path.is_absolute()
        or ".." in path.parts
        or path.name != "script-structure-contract.json"
    ):
        raise BodyStructureValidationError("body_structure_source_contract_ref_invalid")


def _required_text(value: object, blocker: str) -> str:
    if not _is_text(value):
        raise BodyStructureValidationError(blocker)
    return str(value).strip()


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )
