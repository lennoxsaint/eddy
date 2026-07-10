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
    assert json.loads((repair.run_dir / "repair-packet.json").read_text())["remaining_attempts"] == 2
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


def test_third_failed_attempt_becomes_terminal_blocker(tmp_path: Path) -> None:
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

    assert result.state is JobState.BLOCKED
    assert json.loads((job.run_dir / "repair-packet.json").read_text())["remaining_attempts"] == 0


def test_cancelled_job_has_terminal_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)

    cancelled = manager.cancel(job.id)

    assert cancelled.state is JobState.CANCELLED
    assert "job_cancelled" in (cancelled.run_dir / "receipts.jsonl").read_text()
