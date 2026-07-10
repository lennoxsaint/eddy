import json
from pathlib import Path

import pytest

from eddy.plan import EditPlanV3, PlanValidationError
from eddy.runtime import JobManager, JobState


def valid_plan() -> dict:
    return {
        "schema_version": "edit-plan-v3",
        "source_hashes": {"camera.mp4": "a" * 64},
        "protected": [{"start": 10.0, "end": 12.0, "reason": "vulnerable pause"}],
        "body": {"keep": [[5.0, 50.0]], "drop": [[0.0, 5.0]], "retake_groups": []},
        "hooks": [
            {"id": "proof", "rank": 1, "segments": [[50.0, 65.0]], "proof_assets": ["post.png"]},
            {"id": "speed", "rank": 2, "segments": [[70.0, 85.0]], "proof_assets": []},
            {"id": "cost", "rank": 3, "segments": [[90.0, 105.0]], "proof_assets": []},
        ],
        "shorts": [
            {"id": f"short-{index}", "segments": [[float(index), float(index + 1)]]}
            for index in range(3)
        ],
        "motion_beats": [],
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
    three_shorts["shorts"] = [
        {"id": f"s{index}", "segments": [[float(index), float(index + 1)]]}
        for index in range(3)
    ]
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
    assert lock["before"][str(media)]
    assert (job.snapshot / "camera.mp4").read_bytes() == b"raw-media"
    media.write_bytes(b"mutated-after-start")
    assert (job.snapshot / "camera.mp4").read_bytes() == b"raw-media"


def test_red_attempt_is_quarantined_and_never_promoted(tmp_path: Path) -> None:
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

    blocked = manager.record_verification(
        job.id,
        attempt=attempt,
        gates={"audio_effect_survival": False, "source_lock": True},
        blockers=["descript_effect_not_rendered"],
    )

    assert blocked.state is JobState.BLOCKED
    assert (blocked.run_dir / "quarantine" / "attempt-1" / "long-primary.mp4").exists()
    assert not (blocked.run_dir / "final").exists()


def test_missing_required_verification_gates_can_never_promote(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    attempt = job.run_dir / "work" / "attempt-1"
    attempt.mkdir(parents=True)
    (attempt / "long-primary.mp4").write_bytes(b"candidate")

    blocked = manager.record_verification(job.id, attempt=attempt, gates={}, blockers=[])

    assert blocked.state is JobState.BLOCKED
    assert "required_gate_missing:three_long_variants" in blocked.blockers
    assert not (blocked.run_dir / "final").exists()


def test_cancelled_job_has_terminal_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-media")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)

    cancelled = manager.cancel(job.id)

    assert cancelled.state is JobState.CANCELLED
    assert "job_cancelled" in (cancelled.run_dir / "receipts.jsonl").read_text()
