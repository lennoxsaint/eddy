import json
from pathlib import Path

import pytest

from eddy.plan import EditPlanV3, PlanValidationError
from eddy.runtime import JobManager, JobState


def valid_plan() -> dict:
    return {
        "schema_version": "edit-plan-v3",
        "source_hashes": {"camera.mp4": "a" * 64, "screen.mp4": "b" * 64},
        "protected": [{"start": 10.0, "end": 12.0, "reason": "vulnerable pause"}],
        "editorial_review": {
            "coverage": [[0.0, 105.0]],
            "resolutions": [
                {
                    "candidate_id": "repeat-1",
                    "action": "keep_variant",
                    "selected_variant_id": "repeat-1-b",
                    "reason": "The later take is complete.",
                }
            ],
        },
        "body": {
            "keep": [[5.0, 50.0]],
            "drop": [[0.0, 5.0]],
            "retake_groups": [
                {
                    "id": "repeat-1",
                    "selected_variant_id": "repeat-1-b",
                    "variants": [
                        {"id": "repeat-1-a", "start": 20.0, "end": 22.0},
                        {"id": "repeat-1-b", "start": 24.0, "end": 26.0},
                    ],
                }
            ],
        },
        "hooks": [
            {"id": "proof", "rank": 1, "segments": [[50.0, 65.0]], "proof_assets": ["post.png"]},
            {"id": "speed", "rank": 2, "segments": [[70.0, 85.0]], "proof_assets": []},
            {"id": "cost", "rank": 3, "segments": [[90.0, 105.0]], "proof_assets": []},
        ],
        "shorts": [
            {
                "id": f"short-{index}",
                "segments": [[float(index), float(index + 1)]],
                "screen_proof_segments": [[float(index), float(index) + 0.25]],
                "motion_beats": [
                    {"id": "hook", "start": 0.0, "dur": 0.2, "layout": "stat", "label": "HOOK"},
                    {"id": "proof", "start": 0.5, "dur": 0.2, "layout": "stat", "label": "PROOF"},
                ],
            }
            for index in range(3)
        ],
        "motion_beats": [
            {
                "id": "long-hook",
                "hook_id": "*",
                "start": 0.0,
                "dur": 0.8,
                "layout": "stat",
                "value": "HOOK",
            },
            {
                "id": "long-proof",
                "hook_id": "*",
                "start": 3.0,
                "dur": 0.8,
                "layout": "image",
                "label": "PROOF",
            },
        ],
    }


def valid_plan_v31() -> dict:
    payload = valid_plan()
    payload["schema_version"] = "edit-plan-v3.1"
    beats = []
    variants = []
    for hook_index, hook in enumerate(payload["hooks"]):
        beat_ids = []
        for beat_index in range(8):
            beat_id = f"{hook['id']}-opening-beat-{beat_index + 1}"
            beat_ids.append(beat_id)
            beats.append(
                {
                    "id": beat_id,
                    "hook_id": hook["id"],
                    "start": beat_index * 3.5,
                    "dur": 2.4,
                    "layout": "stat",
                    "job": "opening_proof_trailer",
                    "source_kind": "real_proof" if beat_index < 3 else "hyperframes",
                    "source_ref": f"proof/opening-{hook_index + 1}-{beat_index + 1}.png",
                    "meaningful_change": f"Reveal state {beat_index + 1}",
                    "preview_safe": True,
                    "value": str(beat_index + 1),
                }
            )
        variants.append(
            {
                "variant_id": f"opening-{hook_index + 1}",
                "hook_id": hook["id"],
                "money_shot_by_second": 3,
                "proof_by_second": 8,
                "stakes_by_second": 26,
                "meaningful_visual_beat_ids": beat_ids,
                "max_unexplained_static_hold_seconds": 3.5,
                "muted_preview_status": "pass",
                "mobile_preview_status": "pass",
                "taste_review_status": "pass",
                "outlier_visual_refs": [f"observed-outlier-{hook_index + 1}"],
                "tldraw_mode": "none",
            }
        )
    payload["motion_beats"] = beats
    payload["opening_visual_contract"] = {
        "schema_version": "1.0",
        "profile_version": 5,
        "contract_ref": "pre-production/review/opening-visual-contract.json",
        "contract_sha256": "c" * 64,
        "comparison_reel_ref": "source/eddy/opening-comparison-reel.mp4",
        "contact_sheet_ref": "source/eddy/opening-contact-sheet.png",
        "variants": variants,
    }
    return payload


def _scene(
    scene_id: str,
    start: float,
    end: float,
    *,
    job: str = "explain",
    layout: str = "speaker_full",
    authority: str = "raw_source",
    transition: str = "hard_cut",
    reason: str | None = None,
) -> dict:
    scene = {
        "id": scene_id,
        "start": start,
        "end": end,
        "speech_anchor": f"speech-{scene_id}",
        "semantic_job": job,
        "meaningful_change": f"Change the visual argument for {scene_id}",
        "layout": layout,
        "evidence_authority": authority,
        "source_refs": ["camera.mp4"],
        "motion_verb": "reveal",
        "transition": transition,
        "cause": "The spoken claim changes.",
        "preview_safe": True,
    }
    if reason is not None:
        scene["quiet_hold_reason"] = reason
    return scene


def valid_plan_v32() -> dict:
    payload = valid_plan_v31()
    payload["schema_version"] = "edit-plan-v3.2"
    payload["hooks"][0]["segments"] = [[50.0, 80.0]]
    payload["hooks"][1]["segments"] = [[70.0, 100.0]]
    payload["hooks"][2]["segments"] = [[75.0, 105.0]]
    for index, short in enumerate(payload["shorts"]):
        start = float(index * 12)
        short["segments"] = [[start, start + 12.0]]
        short["screen_proof_segments"] = [[start, start + 3.0]]
    openings = []
    opening_layouts = [
        "proof_canvas",
        "speaker_edge_right",
        "source_screen",
        "speaker_full",
        "illustration_canvas",
        "speaker_pip",
        "proof_canvas",
        "special_emphasis",
    ]
    opening_jobs = [
        "frame_one",
        "money_shot",
        "proof",
        "explain",
        "stakes",
        "proof",
        "explain",
        "stakes",
    ]
    opening_starts = [0.0, 1.5, 3.0, 6.5, 10.0, 13.5, 18.0, 23.0]
    for hook_index, hook in enumerate(payload["hooks"]):
        scenes = []
        for index, (layout, job) in enumerate(zip(opening_layouts, opening_jobs, strict=True)):
            start = opening_starts[index]
            end = opening_starts[index + 1] if index < 7 else 30.0
            scenes.append(
                _scene(
                    f"{hook['id']}-scene-{index + 1}",
                    start,
                    end,
                    job=job,
                    layout=layout,
                    authority="supplied_asset" if job in {"money_shot", "proof"} else "raw_source",
                    reason=(
                        "Let the viewer inspect the proof."
                        if index in {1, 5, 6, 7}
                        else None
                    ),
                )
            )
        openings.append(
            {
                "id": f"opening-{hook_index + 1}",
                "hook_id": hook["id"],
                "ranking_signals": {
                    "frame_one": 1.0,
                    "money_shot": 1.0,
                    "proof": 1.0,
                    "stakes": 1.0,
                    "muted": 1.0,
                    "mobile": (1.0, 0.7, 0.0)[hook_index],
                    "semantic_density": (1.0, 1.0, 0.5)[hook_index],
                    "taste": (1.0, 0.0, 0.0)[hook_index],
                },
                "ranking_evidence": [f"opening-review-{hook_index + 1}.json"],
                "rank_confidence": "certain",
                "scenes": scenes,
            }
        )

    body_scenes = [
        _scene(
            f"body-{index + 1}",
            index * 8.0,
            43.0 if index == 5 else (index + 1) * 8.0,
            layout=("speaker_full", "source_screen", "speaker_edge_left")[index % 3],
            reason="The proof needs uninterrupted reading time." if index == 1 else None,
        )
        for index in range(6)
    ]
    portrait_scenes = [
        _scene(
            f"short-scene-{index + 1}",
            index * 1.0,
            12.0 if index == 7 else (index + 1) * 1.0,
            job=("frame_one", "money_shot", "proof", "explain")[min(index, 3)],
            layout=("speaker_full", "proof_canvas", "speaker_pip", "source_screen")[index % 4],
        )
        for index in range(8)
    ]
    payload["frame_contract"] = {
        "schema_version": "eddy-project-frame-v1",
        "ref": "frame.md",
        "sha256": "d" * 64,
    }
    payload["visual_choreography"] = {
        "schema_version": "eddy-visual-choreography-v1",
        "openings": openings,
        "shared_body": {"id": "shared-body", "scenes": body_scenes},
        "shorts": [
            {"short_id": short["id"], "scenes": portrait_scenes}
            for short in payload["shorts"]
        ],
    }
    return payload


def valid_plan_v33() -> dict:
    payload = valid_plan_v32()
    payload["schema_version"] = "edit-plan-v3.3"
    body_scenes = payload["visual_choreography"]["shared_body"]["scenes"]
    body_scenes[2]["semantic_job"] = "reset"
    body_scenes[4]["semantic_job"] = "reset"
    for section_id, scene_indexes in (
        ("SEC-01", (0, 1)),
        ("SEC-02", (2, 3)),
        ("SEC-03", (4, 5)),
    ):
        for scene_index in scene_indexes:
            body_scenes[scene_index]["body_section_id"] = section_id
    payload["body_structure_contract"] = {
        "schema_version": "eddy-body-structure-v1",
        "source_contract_ref": "pre-production/review/script-structure-contract.json#body_structure",
        "source_contract_sha256": "e" * 64,
        "major_order_authority": "sage_locked_eddy_may_not_reorder",
        "mode": "live_test",
        "route_contract": {
            "proof": "Four operators rejected the first report.",
            "promise": "The viewer gets one test for deciding whether an AI workflow works.",
            "plan": "Run the workflow through three increasingly consequential tests.",
            "understood_by_second": 28,
            "progress_unit": "round",
            "section_ids": ["SEC-01", "SEC-02", "SEC-03"],
        },
        "sections": [
            {
                "section_id": "SEC-01",
                "label": "The failure",
                "question": "Why did the first run fail?",
                "scene_ids": ["body-1", "body-2"],
                "proof_scene_ids": ["body-2"],
                "payoff": "The first run optimized the wrong result.",
                "viewer_action": "Name the decision before running the tool.",
                "next_loop": "Can the corrected run change a real decision?",
                "story_role": "evidence",
                "story_source_ref": "receipt:R-01",
            },
            {
                "section_id": "SEC-02",
                "label": "The rerun",
                "question": "Can the corrected run survive the receipt test?",
                "scene_ids": ["body-3", "body-4"],
                "proof_scene_ids": ["body-4"],
                "payoff": "The rerun names one defensible workflow.",
                "viewer_action": "Compare the recommendation with the action log.",
                "next_loop": "Will Lennox actually change the workflow?",
                "story_role": "none",
                "story_source_ref": None,
            },
            {
                "section_id": "SEC-03",
                "label": "The verdict",
                "question": "Does the recommendation cause action?",
                "scene_ids": ["body-5", "body-6"],
                "proof_scene_ids": ["body-6"],
                "payoff": "The workflow changes from active to paused.",
                "viewer_action": "Run the same consequence test on one workflow.",
                "next_loop": None,
                "story_role": "decision",
                "story_source_ref": "screen:workflow-status",
            },
        ],
        "progress_cues": [
            {
                "after_section_id": "SEC-01",
                "scene_id": "body-3",
                "transition_card": "1 of 3: Failure",
                "spoken_callback": "The first run failed. Now the rerun has to change a decision.",
            },
            {
                "after_section_id": "SEC-02",
                "scene_id": "body-5",
                "transition_card": "2 of 3: Rerun",
                "spoken_callback": "The rerun passed. Now it has to cause action.",
            },
        ],
        "final_payoff": {
            "section_id": "SEC-03",
            "verdict": "The workflow only keeps its job if it changes operating state.",
            "resulting_action": "Pause the workflow for seven days.",
            "earned_cta_relationship": "Invite the viewer after the reusable test is complete.",
        },
    }
    return payload


def valid_plan_v34() -> dict:
    payload = valid_plan_v33()
    payload["schema_version"] = "edit-plan-v3.4"
    payload["frame_contract"]["schema_version"] = "eddy-project-frame-v2"
    payload["contract_bundle"] = {
        "schema_version": "eddy-contract-bundle-ref-v1",
        "ref": "contracts/contract-bundle.json",
        "sha256": "f" * 64,
    }
    payload["audio_plan"] = {
        "schema_version": "eddy-audio-plan-v1",
        "music": [
            {
                "ref": "assets/audio/music.wav",
                "provenance": "local",
                "license": "owned",
                "cue": "0-end",
                "purpose": "upbeat_lofi_bed",
                "mix_db": -24,
            }
        ],
        "sfx": [
            {
                "ref": "assets/audio/click.wav",
                "provenance": "bundled",
                "license": "CC0",
                "cue": "1.25",
                "purpose": "state_change",
                "mix_db": -18,
            }
        ],
        "paid_retrieval_allowed": False,
    }
    payload["grade_plan"] = {
        "schema_version": "eddy-grade-plan-v1",
        "camera_goal": "natural_skin_exposure_white_balance_consistency",
        "screen_recording_policy": "preserve_source_color_fidelity",
        "shot_checks": ["camera-a"],
    }
    payload["caption_policy"] = {
        "schema_version": "eddy-caption-policy-v1",
        "prior_words": "visible",
        "active_word": "highlighted",
        "future_words": "invisible",
        "source_caption_collision": "suppress_eddy_captions",
        "source_caption_intervals": {"short-0": [[0.0, 1.0]]},
    }
    payload["production_review"] = {
        "schema_version": "eddy-production-review-v1",
        "minimum_complete_passes": 3,
        "target_score": 100,
        "maximum_score": 100,
        "audience_performance": "NOT_RUN",
        "final_authority": "owner_taste_lock",
        "repair_policy": "change_strategy_until_green_or_exact_blocker",
        "strategy_id": "opening-proof-route-v1",
    }
    return payload


def plan_for_job(job) -> dict:
    payload = valid_plan()
    lock = json.loads((job.run_dir / "source-lock.json").read_text())
    payload["source_hashes"] = lock["before"]
    return payload


def test_edit_plan_requires_three_ranked_hooks_and_one_body() -> None:
    plan = EditPlanV3.from_dict(valid_plan())

    assert plan.primary_hook.id == "proof"
    assert [hook.id for hook in plan.alternate_hooks] == ["speed", "cost"]
    assert plan.body.keep == ((5.0, 50.0),)
    assert plan.body.retake_groups[0].selected_variant_id == "repeat-1-b"
    assert plan.editorial_review.resolutions[0].candidate_id == "repeat-1"


def test_privacy_mask_is_hook_scoped_and_survives_round_trip() -> None:
    payload = valid_plan()
    payload["privacy_masks"] = [
        {
            "id": "bystander-comment",
            "hook_ids": ["proof"],
            "start": 0.0,
            "end": 18.7,
            "x": 175,
            "y": 920,
            "width": 790,
            "height": 160,
            "color": "0x111827",
        }
    ]

    plan = EditPlanV3.from_dict(payload)

    assert plan.privacy_masks[0].hook_ids == ("proof",)
    assert plan.to_dict()["privacy_masks"] == payload["privacy_masks"]


def test_privacy_mask_rejects_unknown_hook_and_out_of_bounds_rectangle() -> None:
    unknown_hook = valid_plan()
    unknown_hook["privacy_masks"] = [
        {
            "id": "bystander-comment",
            "hook_ids": ["missing"],
            "start": 0.0,
            "end": 18.7,
            "x": 175,
            "y": 920,
            "width": 790,
            "height": 160,
            "color": "0x111827",
        }
    ]
    with pytest.raises(PlanValidationError, match="privacy_mask_hook_unknown"):
        EditPlanV3.from_dict(unknown_hook)

    out_of_bounds = valid_plan()
    out_of_bounds["privacy_masks"] = [
        {
            "id": "bystander-comment",
            "hook_ids": ["proof"],
            "start": 0.0,
            "end": 18.7,
            "x": 175,
            "y": 1000,
            "width": 790,
            "height": 160,
            "color": "0x111827",
        }
    ]
    with pytest.raises(PlanValidationError, match="privacy_mask_rectangle_out_of_bounds"):
        EditPlanV3.from_dict(out_of_bounds)


def test_short_drop_is_source_bounded_and_survives_round_trip() -> None:
    payload = valid_plan()
    payload["shorts"][0]["segments"] = [[0.0, 2.0]]
    payload["shorts"][0]["drop"] = [[0.4, 0.8]]
    payload["shorts"][0]["screen_proof_segments"] = [[0.8, 1.4]]

    plan = EditPlanV3.from_dict(payload)

    assert plan.shorts[0].drop == ((0.4, 0.8),)
    assert plan.to_dict()["shorts"][0]["drop"] == [[0.4, 0.8]]

    payload["shorts"][0]["drop"] = [[1.9, 2.1]]
    with pytest.raises(PlanValidationError, match="short_drop_outside_segments"):
        EditPlanV3.from_dict(payload)


def test_short_drop_cannot_erase_candidate_or_protected_content() -> None:
    erased = valid_plan()
    erased["shorts"][0]["drop"] = [[0.0, 1.0]]
    with pytest.raises(PlanValidationError, match="short_drop_removes_entire_candidate"):
        EditPlanV3.from_dict(erased)

    protected = valid_plan()
    protected["shorts"][0]["segments"] = [[10.0, 13.0]]
    protected["shorts"][0]["drop"] = [[10.5, 11.0]]
    protected["shorts"][0]["screen_proof_segments"] = [[11.0, 12.0]]
    with pytest.raises(PlanValidationError, match="short_drop_overlaps_protected_span"):
        EditPlanV3.from_dict(protected)


def test_edit_plan_rejects_packaging_and_missing_alternate() -> None:
    payload = valid_plan()
    payload["hooks"] = payload["hooks"][:2]
    payload["title"] = "not in v3"

    with pytest.raises(PlanValidationError):
        EditPlanV3.from_dict(payload)


def test_edit_plan_requires_three_to_five_shorts() -> None:
    zero_shorts = valid_plan()
    zero_shorts["shorts"] = []
    with pytest.raises(PlanValidationError, match="shorts_count_must_be_3_to_5"):
        EditPlanV3.from_dict(zero_shorts)

    one_short = valid_plan()
    one_short["shorts"] = [{"id": "s1", "segments": [[1.0, 2.0]]}]

    with pytest.raises(PlanValidationError, match="shorts_count_must_be_3_to_5"):
        EditPlanV3.from_dict(one_short)

    three_shorts = valid_plan()
    assert len(EditPlanV3.from_dict(three_shorts).shorts) == 3


def test_edit_plan_rejects_nonfinite_ranges_and_duplicate_short_ids() -> None:
    nonfinite = valid_plan()
    nonfinite["body"]["keep"] = [[0.0, float("inf")]]
    with pytest.raises(PlanValidationError, match="body_keep_range_invalid"):
        EditPlanV3.from_dict(nonfinite)

    duplicate = valid_plan()
    duplicate["shorts"][1]["id"] = duplicate["shorts"][0]["id"]
    with pytest.raises(PlanValidationError, match="short_ids_must_be_unique"):
        EditPlanV3.from_dict(duplicate)


def test_edit_plan_requires_resolved_editorial_review() -> None:
    missing_review = valid_plan()
    missing_review.pop("editorial_review")
    with pytest.raises(PlanValidationError, match="editorial_review_required"):
        EditPlanV3.from_dict(missing_review)

    unresolved = valid_plan()
    unresolved["editorial_review"]["resolutions"][0]["reason"] = ""
    with pytest.raises(PlanValidationError, match="editorial_resolution_reason_required"):
        EditPlanV3.from_dict(unresolved)


def test_dual_source_short_contract_requires_screen_share_and_two_motion_beats() -> None:
    too_little_proof = valid_plan()
    too_little_proof["shorts"][0]["screen_proof_segments"] = [[0.0, 0.1]]
    with pytest.raises(PlanValidationError, match="short_screen_proof_below_25_percent"):
        EditPlanV3.from_dict(too_little_proof)

    one_beat = valid_plan()
    one_beat["shorts"][0]["motion_beats"] = one_beat["shorts"][0]["motion_beats"][:1]
    with pytest.raises(PlanValidationError, match="short_two_motion_beats_required"):
        EditPlanV3.from_dict(one_beat)


def test_long_motion_plan_must_cover_every_hook() -> None:
    no_motion = valid_plan()
    no_motion["motion_beats"] = []

    with pytest.raises(PlanValidationError, match="long_two_motion_beats_required"):
        EditPlanV3.from_dict(no_motion)


def test_edit_plan_v31_requires_three_complete_opening_proof_trailers() -> None:
    payload = valid_plan_v31()

    plan = EditPlanV3.from_dict(payload)

    assert plan.schema_version == "edit-plan-v3.1"
    assert plan.opening_visual_contract is not None
    assert len(plan.opening_visual_contract["variants"]) == 3
    assert plan.to_dict()["opening_visual_contract"] == payload["opening_visual_contract"]


def test_edit_plan_v31_rejects_missing_or_late_opening_proof() -> None:
    missing = valid_plan_v31()
    missing.pop("opening_visual_contract")
    with pytest.raises(PlanValidationError, match="opening_visual_contract_required"):
        EditPlanV3.from_dict(missing)

    late = valid_plan_v31()
    late["opening_visual_contract"]["variants"][0]["money_shot_by_second"] = 3.1
    with pytest.raises(PlanValidationError, match="opening_money_shot_must_arrive_by_three_seconds"):
        EditPlanV3.from_dict(late)


def test_edit_plan_v31_binds_eight_semantic_beats_to_each_hook() -> None:
    too_few = valid_plan_v31()
    too_few["opening_visual_contract"]["variants"][1][
        "meaningful_visual_beat_ids"
    ] = too_few["opening_visual_contract"]["variants"][1][
        "meaningful_visual_beat_ids"
    ][:7]
    with pytest.raises(PlanValidationError, match="opening_eight_meaningful_beats_required"):
        EditPlanV3.from_dict(too_few)

    missing_semantics = valid_plan_v31()
    missing_semantics["motion_beats"][0].pop("meaningful_change")
    with pytest.raises(PlanValidationError, match="long_motion_semantic_fields_required"):
        EditPlanV3.from_dict(missing_semantics)


def test_edit_plan_v32_accepts_hash_bound_full_frame_choreography() -> None:
    payload = valid_plan_v32()

    plan = EditPlanV3.from_dict(payload)

    assert plan.schema_version == "edit-plan-v3.2"
    assert plan.frame_contract == payload["frame_contract"]
    assert plan.visual_choreography == payload["visual_choreography"]
    assert plan.to_dict()["visual_choreography"]["shared_body"]["id"] == "shared-body"


def test_edit_plan_v33_accepts_locked_body_spine_and_round_trips() -> None:
    payload = valid_plan_v33()

    plan = EditPlanV3.from_dict(payload)

    assert plan.schema_version == "edit-plan-v3.3"
    assert plan.body_structure_contract == payload["body_structure_contract"]
    assert plan.to_dict()["body_structure_contract"]["route_contract"]["section_ids"] == [
        "SEC-01",
        "SEC-02",
        "SEC-03",
    ]


def test_edit_plan_v33_requires_body_contract_and_three_to_five_sections() -> None:
    missing = valid_plan_v33()
    missing.pop("body_structure_contract")
    with pytest.raises(PlanValidationError, match="body_structure_contract_required"):
        EditPlanV3.from_dict(missing)

    too_few = valid_plan_v33()
    too_few["body_structure_contract"]["sections"] = too_few["body_structure_contract"]["sections"][:2]
    with pytest.raises(PlanValidationError, match="body_structure_sections_must_be_3_to_5"):
        EditPlanV3.from_dict(too_few)


def test_edit_plan_v33_rejects_reordered_or_unmapped_body_scenes() -> None:
    reordered = valid_plan_v33()
    reordered["body_structure_contract"]["sections"].reverse()
    with pytest.raises(PlanValidationError, match="body_structure_section_order_mismatch"):
        EditPlanV3.from_dict(reordered)

    unmapped = valid_plan_v33()
    unmapped["body_structure_contract"]["sections"][-1]["scene_ids"].pop()
    unmapped["body_structure_contract"]["sections"][-1]["proof_scene_ids"] = ["body-5"]
    with pytest.raises(PlanValidationError, match="body_structure_scene_coverage_mismatch"):
        EditPlanV3.from_dict(unmapped)


def test_edit_plan_v33_requires_proof_and_progress_cues() -> None:
    no_proof = valid_plan_v33()
    no_proof["body_structure_contract"]["sections"][0]["proof_scene_ids"] = []
    with pytest.raises(PlanValidationError, match="body_structure_proof_scene_required"):
        EditPlanV3.from_dict(no_proof)

    no_cue = valid_plan_v33()
    no_cue["body_structure_contract"]["progress_cues"].pop()
    with pytest.raises(PlanValidationError, match="body_structure_progress_cues_mismatch"):
        EditPlanV3.from_dict(no_cue)


def test_edit_plan_v33_rejects_background_biography_and_editor_reordering_authority() -> None:
    biography = valid_plan_v33()
    biography["body_structure_contract"]["sections"][0]["story_role"] = "background"
    with pytest.raises(PlanValidationError, match="body_structure_story_role_invalid"):
        EditPlanV3.from_dict(biography)

    authority = valid_plan_v33()
    authority["body_structure_contract"]["major_order_authority"] = "eddy_may_reorder"
    with pytest.raises(PlanValidationError, match="body_structure_major_order_authority_invalid"):
        EditPlanV3.from_dict(authority)


def test_edit_plan_v32_rejects_late_money_shot_and_body_cadence_gap() -> None:
    late = valid_plan_v32()
    late["visual_choreography"]["openings"][0]["scenes"][0]["end"] = 3.1
    late["visual_choreography"]["openings"][0]["scenes"][1]["start"] = 3.1
    late["visual_choreography"]["openings"][0]["scenes"][1]["end"] = 3.2
    late["visual_choreography"]["openings"][0]["scenes"][2]["start"] = 3.2
    with pytest.raises(PlanValidationError, match="opening_money_shot_must_arrive_by_three_seconds"):
        EditPlanV3.from_dict(late)

    sparse = valid_plan_v32()
    sparse["visual_choreography"]["shared_body"]["scenes"][0]["end"] = 13.0
    sparse["visual_choreography"]["shared_body"]["scenes"][1]["start"] = 13.0
    with pytest.raises(PlanValidationError, match="visual_state_change_exceeds_twelve_seconds"):
        EditPlanV3.from_dict(sparse)

    incomplete = valid_plan_v32()
    incomplete["visual_choreography"]["openings"][0]["scenes"][-1]["end"] = 29.0
    with pytest.raises(
        PlanValidationError,
        match="opening_choreography_must_cover_complete_hook:proof",
    ):
        EditPlanV3.from_dict(incomplete)

    short_incomplete = valid_plan_v32()
    short_incomplete["visual_choreography"]["shorts"][0]["scenes"][-1]["end"] = 11.0
    with pytest.raises(
        PlanValidationError,
        match="portrait_choreography_must_cover_complete_short:short-0",
    ):
        EditPlanV3.from_dict(short_incomplete)


def test_protected_span_cannot_be_dropped_or_omitted_from_shared_body() -> None:
    omitted = valid_plan()
    omitted["body"]["keep"] = [[20.0, 50.0]]
    with pytest.raises(PlanValidationError, match="protected_span_missing_from_shared_body"):
        EditPlanV3.from_dict(omitted)

    dropped = valid_plan()
    dropped["body"]["drop"] = [[11.0, 11.5]]
    with pytest.raises(PlanValidationError, match="body_drop_overlaps_protected_span"):
        EditPlanV3.from_dict(dropped)


def test_job_start_hashes_sources_and_never_writes_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    media = source / "camera.mp4"
    media.write_bytes(b"raw-media")
    before = sorted(source.iterdir())
    manager = JobManager(tmp_path / "runs")

    job = manager.start(source)

    assert job.state is JobState.QUEUED
    assert sorted(source.iterdir()) == before
    lock = json.loads((job.run_dir / "source-lock.json").read_text())
    assert lock["before"]["camera.mp4"]
    assert (job.snapshot / "camera.mp4").read_bytes() == b"raw-media"
    media.write_bytes(b"mutated-after-start")
    assert (job.snapshot / "camera.mp4").read_bytes() == b"raw-media"


def test_completed_job_can_be_reopened_for_one_receipted_owner_repair(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    final = job.run_dir / "final"
    final.mkdir()
    (final / "long-primary.mp4").write_bytes(b"candidate")
    state = json.loads((job.run_dir / "state.json").read_text())
    state["state"] = "completed"
    (job.run_dir / "state.json").write_text(json.dumps(state))

    reopened = manager.request_owner_repair(
        job.id,
        reason="Incidental bystander comment must be redacted before staging.",
    )

    assert reopened.state is JobState.AWAITING_HOST_REPAIR
    assert not final.exists()
    assert (job.run_dir / "quarantine" / "attempt-1" / "long-primary.mp4").exists()
    packet = json.loads((job.run_dir / "repair-packet.json").read_text())
    assert packet["blockers"] == ["owner_directed_repair"]
    assert packet["remaining_attempts"] is None
    assert packet["minimum_complete_passes"] == 3


def test_owner_repair_after_third_attempt_still_requests_changed_strategy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    quarantine = job.run_dir / "quarantine"
    (quarantine / "attempt-1").mkdir(parents=True)
    (quarantine / "attempt-2").mkdir()
    final = job.run_dir / "final"
    final.mkdir()
    (final / "long-primary.mp4").write_bytes(b"candidate")
    state = json.loads((job.run_dir / "state.json").read_text())
    state["state"] = "completed"
    (job.run_dir / "state.json").write_text(json.dumps(state))

    repair = manager.request_owner_repair(
        job.id,
        reason="The third treatment still needs a different proof route.",
    )

    assert repair.state is JobState.AWAITING_HOST_REPAIR
    assert repair.blockers == ("owner_directed_repair",)
    assert not final.exists()
    assert (quarantine / "attempt-3" / "long-primary.mp4").is_file()


def test_top_level_raw_media_excludes_nested_prior_run_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "raw"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"camera")
    (source / "screen.mp4").write_bytes(b"screen")
    prior = source / "eddy-runs" / "old" / "final"
    prior.mkdir(parents=True)
    (prior / "video.mp4").write_bytes(b"derived")
    manager = JobManager(tmp_path / "runs")

    job = manager.start(source)

    lock = json.loads((job.run_dir / "source-lock.json").read_text())
    assert set(lock["before"]) == {"camera.mp4", "screen.mp4"}
    assert not (job.snapshot / "eddy-runs").exists()


def test_host_submission_blocks_unreviewed_editorial_candidate(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    job = manager.transition(job.id, JobState.AWAITING_HOST_PLAN)
    (job.run_dir / "editorial-ledger.json").write_text(
        json.dumps(
            {
                "chunks": [{"id": "chunk-001", "start": 0.0, "end": 10.0, "text": "text"}],
                "candidates": [
                    {"id": "missing-repeat", "kind": "repeat", "requires_resolution": True}
                ],
            }
        )
        + "\n"
    )
    payload = plan_for_job(job)

    with pytest.raises(PlanValidationError, match="editorial_candidate_unresolved:missing-repeat"):
        manager.submit_plan(job.id, payload)


def test_red_attempt_is_quarantined_and_requests_host_repair(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    job = manager.transition(job.id, JobState.AWAITING_HOST_PLAN)
    manager.submit_plan(job.id, plan_for_job(job))
    attempt = job.run_dir / "work" / "attempt-1"
    attempt.mkdir(parents=True)
    (attempt / "long-primary.mp4").write_bytes(b"proxy")

    repair = manager.record_verification(
        job.id,
        attempt=attempt,
        gates={"audio_effect_survival": False, "source_lock": True},
        blockers=["descript_effect_not_rendered"],
    )

    assert repair.state is JobState.AWAITING_HOST_REPAIR
    assert (repair.run_dir / "quarantine" / "attempt-1" / "long-primary.mp4").exists()
    assert (
        json.loads((repair.run_dir / "repair-packet.json").read_text())["remaining_attempts"]
        is None
    )
    assert not (repair.run_dir / "final").exists()


def test_missing_required_verification_gates_can_never_promote(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    attempt = job.run_dir / "work" / "attempt-1"
    attempt.mkdir(parents=True)
    (attempt / "long-primary.mp4").write_bytes(b"candidate")

    repair = manager.record_verification(job.id, attempt=attempt, gates={}, blockers=[])

    assert repair.state is JobState.AWAITING_HOST_REPAIR
    assert "required_gate_missing:three_long_variants" in repair.blockers
    assert not (repair.run_dir / "final").exists()


def test_third_failed_attempt_still_requests_a_changed_strategy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)

    result = job
    for attempt_number in range(1, 4):
        result = manager.transition(job.id, JobState.VERIFYING)
        attempt = job.run_dir / "work" / f"attempt-{attempt_number}"
        attempt.mkdir(parents=True)
        (attempt / "candidate.mp4").write_bytes(b"candidate")
        result = manager.record_verification(
            job.id,
            attempt=attempt,
            gates={},
            blockers=["retake_clean_failed"],
        )

    assert result.state is JobState.AWAITING_HOST_REPAIR
    packet = json.loads((job.run_dir / "repair-packet.json").read_text())
    assert packet["remaining_attempts"] is None
    assert packet["repair_policy"] == "change_strategy_until_green_or_exact_blocker"


def test_v34_requires_all_bound_production_contracts() -> None:
    plan = EditPlanV3.from_dict(valid_plan_v34())

    assert plan.schema_version == "edit-plan-v3.4"
    assert plan.contract_bundle is not None
    assert plan.audio_plan is not None
    assert plan.grade_plan is not None
    assert plan.caption_policy is not None
    assert plan.production_review is not None

    missing = valid_plan_v34()
    del missing["audio_plan"]
    with pytest.raises(PlanValidationError, match="audio_plan_schema_invalid"):
        EditPlanV3.from_dict(missing)


def test_cancelled_job_has_terminal_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)

    cancelled = manager.cancel(job.id)

    assert cancelled.state is JobState.CANCELLED
    assert "job_cancelled" in (cancelled.run_dir / "receipts.jsonl").read_text()
