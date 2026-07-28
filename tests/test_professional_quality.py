from __future__ import annotations

import json
from pathlib import Path

import pytest

from eddy.design_contracts import (
    DesignContractError,
    create_contract_bundle,
    revise_contract_bundle,
)
from eddy.quality import (
    QualityContractError,
    resolve_quality_profile,
    validate_audio_plan,
    validate_caption_policy,
    validate_contract_ref,
    validate_grade_plan,
    validate_production_review,
)
from eddy.runtime import _contract_binding_evidence, _production_evidence


ROOT = Path(__file__).resolve().parents[1]


def test_professional_rubric_is_ten_categories_of_ten_evidenced_points() -> None:
    rubric = json.loads(
        (ROOT / "evals" / "professional-youtube-100-rubric.json").read_text()
    )

    assert rubric["maximum_score"] == rubric["passing_score"] == 100
    assert rubric["points_per_check"] == 1
    assert len(rubric["categories"]) == 10
    assert all(row["points"] == 10 and len(row["checks"]) == 10 for row in rubric["categories"])
    assert set(rubric["evidence_types"]) == {
        "file",
        "frame",
        "timestamp",
        "hash",
        "playback",
        "measurement",
    }


def test_correction_evals_cover_recovered_professional_failures() -> None:
    payload = json.loads(
        (ROOT / "evals" / "professional-youtube-corrections-v1.json").read_text()
    )
    ids = {row["id"] for row in payload["cases"]}

    assert {
        "duplicate-takes",
        "long-silence",
        "weak-hook",
        "constructed-proof",
        "wrong-label",
        "tiny-preview",
        "duplicate-captions",
        "obstructed-ui",
        "excessive-text",
        "missing-mental-model",
        "purposeless-transition",
        "purposeless-zoom",
        "missing-music",
        "missing-sfx",
        "missing-grade",
        "weak-short",
        "caption-onset",
        "abrupt-cta",
        "false-perfect-score",
    } <= ids


def test_profile_resolution_prefers_explicit_then_owner_then_generic(tmp_path: Path) -> None:
    owner = tmp_path / "owner-channel.json"
    owner.write_text(json.dumps({"profile_id": "lennox-professional-youtube-v2"}))

    owner_profile, _ = resolve_quality_profile(ROOT, owner_state_path=owner)
    explicit_legacy, _ = resolve_quality_profile(
        ROOT,
        explicit_profile_id="lennox-professional-youtube-v1",
        owner_state_path=owner,
    )
    explicit_generic, _ = resolve_quality_profile(
        ROOT,
        explicit_profile_id="creator_good_v1",
        owner_state_path=owner,
    )
    owner.unlink()
    generic, _ = resolve_quality_profile(ROOT, owner_state_path=owner)

    assert owner_profile["id"] == "lennox-professional-youtube-v2"
    assert explicit_legacy["id"] == "lennox-professional-youtube-v1"
    assert explicit_generic["id"] == "creator_good_v1"
    assert generic["id"] == "creator_good_v1"

    with pytest.raises(QualityContractError, match="quality_profile_unknown"):
        resolve_quality_profile(
            ROOT,
            explicit_profile_id="does-not-exist",
            owner_state_path=owner,
        )


def test_profile_resolution_fails_closed_for_corrupt_or_invalid_profiles(tmp_path: Path) -> None:
    corrupt_owner = tmp_path / "owner-channel.json"
    corrupt_owner.write_text("{")
    generic, _ = resolve_quality_profile(ROOT, owner_state_path=corrupt_owner)
    assert generic["id"] == "creator_good_v1"

    profile_path = tmp_path / "references" / "creator-good-v1.json"
    with pytest.raises(QualityContractError, match="quality_profile_missing"):
        resolve_quality_profile(tmp_path, explicit_profile_id="creator_good_v1")

    profile_path.parent.mkdir()
    profile_path.write_text(
        json.dumps({"schema_version": "eddy-quality-profile-v1", "id": "wrong"})
    )
    with pytest.raises(QualityContractError, match="quality_profile_id_mismatch"):
        resolve_quality_profile(tmp_path, explicit_profile_id="creator_good_v1")

    profile_path.write_text(json.dumps({"schema_version": "unknown", "id": "creator_good_v1"}))
    with pytest.raises(QualityContractError, match="quality_profile_schema_invalid"):
        resolve_quality_profile(tmp_path, explicit_profile_id="creator_good_v1")


def test_v34_contract_reference_validation_covers_success_and_failures() -> None:
    valid = {
        "schema_version": "eddy-contract-bundle-v1",
        "ref": "contracts/contract-bundle.json",
        "sha256": "a" * 64,
    }
    assert validate_contract_ref(
        valid,
        schema="eddy-contract-bundle-v1",
        label="contract_bundle",
    ) == valid

    failures = [
        (None, "contract_bundle_required"),
        ({**valid, "schema_version": "wrong"}, "contract_bundle_schema_invalid"),
        ({**valid, "ref": "../outside.json"}, "contract_bundle_ref_invalid"),
        ({**valid, "sha256": "not-a-hash"}, "contract_bundle_sha256_invalid"),
    ]
    for payload, blocker in failures:
        with pytest.raises(QualityContractError, match=blocker):
            validate_contract_ref(
                payload,
                schema="eddy-contract-bundle-v1",
                label="contract_bundle",
            )


def _valid_audio_plan() -> dict[str, object]:
    cue = {
        "ref": "audio/lofi.wav",
        "provenance": "bundled",
        "license": "owner-cleared",
        "cue": "opening",
        "purpose": "forward motion",
        "mix_db": -24,
    }
    return {
        "schema_version": "eddy-audio-plan-v1",
        "music": [dict(cue)],
        "sfx": [{**cue, "ref": "audio/state-change.wav", "mix_db": -18}],
        "paid_retrieval_allowed": False,
    }


def test_v34_audio_grade_caption_and_review_contracts_fail_closed() -> None:
    audio = _valid_audio_plan()
    assert validate_audio_plan(audio) == audio
    audio_failures = [
        (None, "audio_plan_schema_invalid"),
        ({**audio, "music": []}, "audio_plan_music_required"),
        ({**audio, "sfx": []}, "audio_plan_sfx_required"),
        ({**audio, "music": ["bad-row"]}, "audio_plan_cue_invalid"),
        (
            {
                **audio,
                "music": [{**audio["music"][0], "purpose": ""}],  # type: ignore[index]
            },
            "audio_plan_cue_purpose_required",
        ),
        (
            {
                **audio,
                "music": [{**audio["music"][0], "mix_db": float("inf")}],  # type: ignore[index]
            },
            "audio_plan_cue_mix_db_invalid",
        ),
        (
            {
                **audio,
                "music": [{**audio["music"][0], "ref": "../music.wav"}],  # type: ignore[index]
            },
            "audio_plan_cue_ref_invalid",
        ),
        ({**audio, "paid_retrieval_allowed": True}, "audio_plan_paid_retrieval_must_be_false"),
    ]
    for payload, blocker in audio_failures:
        with pytest.raises(QualityContractError, match=blocker):
            validate_audio_plan(payload)

    grade = {
        "schema_version": "eddy-grade-plan-v1",
        "camera_goal": "natural_skin_exposure_white_balance_consistency",
        "screen_recording_policy": "preserve_source_color_fidelity",
        "shot_checks": ["camera-a"],
    }
    assert validate_grade_plan(grade) == grade
    for payload, blocker in [
        (None, "grade_plan_schema_invalid"),
        ({**grade, "camera_goal": "stylized"}, "grade_plan_camera_goal_invalid"),
        ({**grade, "screen_recording_policy": "grade_all"}, "grade_plan_screen_policy_invalid"),
        ({**grade, "shot_checks": []}, "grade_plan_shot_checks_required"),
    ]:
        with pytest.raises(QualityContractError, match=blocker):
            validate_grade_plan(payload)

    captions = {
        "schema_version": "eddy-caption-policy-v1",
        "prior_words": "visible",
        "active_word": "highlighted",
        "future_words": "invisible",
        "source_caption_collision": "suppress_eddy_captions",
        "source_caption_intervals": {"short-01": [[0.0, 1.5]]},
    }
    assert validate_caption_policy(captions) == captions
    for payload, blocker in [
        (None, "caption_policy_schema_invalid"),
        ({**captions, "future_words": "visible"}, "caption_policy_progressive_contract_invalid"),
        (
            {**captions, "source_caption_intervals": []},
            "caption_policy_source_intervals_invalid",
        ),
        (
            {**captions, "source_caption_intervals": {1: []}},
            "caption_policy_source_intervals_invalid",
        ),
        (
            {**captions, "source_caption_intervals": {"short-01": [[2.0, 1.0]]}},
            "caption_policy_source_interval_invalid",
        ),
    ]:
        with pytest.raises(QualityContractError, match=blocker):
            validate_caption_policy(payload)

    review = {
        "schema_version": "eddy-production-review-v1",
        "minimum_complete_passes": 3,
        "target_score": 100,
        "maximum_score": 100,
        "audience_performance": "NOT_RUN",
        "final_authority": "owner_taste_lock",
        "repair_policy": "change_strategy_until_green_or_exact_blocker",
        "strategy_id": "opening-proof-v2",
    }
    assert validate_production_review(review) == review
    for payload, blocker in [
        (None, "production_review_schema_invalid"),
        ({**review, "minimum_complete_passes": 2}, "production_review_three_passes_required"),
        ({**review, "target_score": 99}, "production_review_score_must_be_100"),
        ({**review, "audience_performance": "PASSED"}, "audience_performance_must_be_not_run"),
        ({**review, "final_authority": "agent"}, "production_review_owner_lock_required"),
        ({**review, "repair_policy": "retry"}, "production_review_repair_policy_invalid"),
        ({**review, "strategy_id": ""}, "production_review_strategy_id_required"),
    ]:
        with pytest.raises(QualityContractError, match=blocker):
            validate_production_review(payload)


def test_missing_or_invalid_production_evidence_fails_closed(tmp_path: Path) -> None:
    run = tmp_path / "run"
    attempt = run / "work" / "attempt-1"
    attempt.mkdir(parents=True)

    missing_gates, missing_blockers = _production_evidence(run, attempt)
    assert not any(missing_gates.values())
    assert "production_review_passes_missing" in missing_blockers
    assert "production_score_missing" in missing_blockers

    (attempt / "review-passes.json").write_text("{")
    (attempt / "production-score.json").write_text("{")
    invalid_gates, invalid_blockers = _production_evidence(run, attempt)
    assert not any(invalid_gates.values())
    assert "production_review_passes_invalid" in invalid_blockers
    assert "production_score_invalid" in invalid_blockers

    binding_gates, binding_blockers = _contract_binding_evidence(
        run,
        {"contract_bundle": {"ref": "contracts/missing.json", "sha256": "a" * 64}},
    )
    assert not any(binding_gates.values())
    assert binding_blockers == ["contract_bundle_binding_invalid"]


def test_design_revision_increments_hash_and_invalidates_dependent_renders(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw")
    run = tmp_path / "run"
    run.mkdir()
    (run / "source-lock.json").write_text(
        json.dumps({"before": {"camera.mp4": "a" * 64}, "snapshot": {}, "after": None})
    )
    profile, profile_path = resolve_quality_profile(
        ROOT,
        explicit_profile_id="lennox-professional-youtube-v1",
        owner_state_path=tmp_path / "missing-owner.json",
    )

    created = create_contract_bundle(
        run,
        source=source,
        canonical_root=ROOT,
        profile=profile,
        profile_path=profile_path,
        source_hashes={"camera.mp4": "a" * 64},
        hyperframes_root=tmp_path / "missing-hyperframes",
    )
    binding_gates, binding_blockers = _contract_binding_evidence(
        run,
        {
            "contract_bundle": {
                "ref": created["ref"],
                "sha256": created["sha256"],
            }
        },
    )
    assert all(binding_gates.values())
    assert binding_blockers == []

    attempt = run / "work" / "attempt-1"
    attempt.mkdir(parents=True)
    (attempt / "review-passes.json").write_text(
        json.dumps(
            {
                "schema_version": "eddy-review-passes-v1",
                "passes": [
                    {
                        "watch_evidence": f"playback-{index}",
                        "critique": f"critique-{index}",
                        "repair": f"repair-{index}",
                    }
                    for index in range(1, 4)
                ],
            }
        )
    )
    rubric = json.loads(
        (ROOT / "evals" / "professional-youtube-100-rubric.json").read_text()
    )
    score_checks = [
        {
            "id": f"{category['id']}-{index:02d}",
            "points": 1,
            "passed": True,
            "evidence": [
                {
                    "type": "playback",
                    "ref": f"review/evidence.json#{category['id']}-{index:02d}",
                }
            ],
        }
        for category in rubric["categories"]
        for index, _ in enumerate(category["checks"], start=1)
    ]
    (attempt / "review").mkdir()
    (attempt / "review" / "evidence.json").write_text(
        json.dumps({"status": "reviewed", "checks": 100})
    )
    (attempt / "production-score.json").write_text(
        json.dumps(
            {
                "schema_version": "eddy-production-score-v1",
                "score": 100,
                "checks": score_checks,
                "audience_performance": "NOT_RUN",
                "final_authority": "owner_taste_lock",
            }
        )
    )
    evidence_gates, evidence_blockers = _production_evidence(run, attempt)
    assert all(evidence_gates.values())
    assert evidence_blockers == []

    old_design_hash = created["design_contracts"]["design"]["sha256"]
    revised_design = (run / "design.md").read_text().replace(
        'accent: "#7C5CFF"',
        'accent: "#FF6B35"',
    )
    revised = revise_contract_bundle(
        run,
        reason="The proof labels need a larger mobile-safe scale.",
        design_markdown=revised_design,
    )

    assert revised["design_contracts"]["design"]["revision"] == 2
    assert revised["design_contracts"]["design"]["sha256"] != old_design_hash
    assert revised["invalidation"]["dependent_renders_invalidated"] is True
    bundle = json.loads((run / "contracts" / "contract-bundle.json").read_text())
    assert bundle["revision_history"][0]["reason"].startswith("The proof labels")
    adherence = json.loads((run / "contracts" / "design-adherence.json").read_text())
    assert adherence["pass"] is True


def test_design_revision_rejects_contract_that_drops_normative_rules(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw")
    run = tmp_path / "run"
    run.mkdir()
    (run / "source-lock.json").write_text(
        json.dumps({"before": {"camera.mp4": "a" * 64}, "snapshot": {}, "after": None})
    )
    profile, profile_path = resolve_quality_profile(
        ROOT,
        explicit_profile_id="lennox-professional-youtube-v2",
        owner_state_path=tmp_path / "missing-owner.json",
    )
    create_contract_bundle(
        run,
        source=source,
        canonical_root=ROOT,
        profile=profile,
        profile_path=profile_path,
        source_hashes={"camera.mp4": "a" * 64},
        hyperframes_root=tmp_path / "missing-hyperframes",
    )

    with pytest.raises(
        DesignContractError,
        match="design_adherence_failed",
    ):
        revise_contract_bundle(
            run,
            reason="Replace the design with an incomplete card.",
            design_markdown="# Not a normative design contract\n",
        )
