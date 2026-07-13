import json
from pathlib import Path

from eddy.service import EddyService


def test_edit_options_returns_one_runnable_skill_first_path(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)

    result = service.edit_options(str(source), format="youtube")

    assert result["requires_choice"] is False
    assert result["selected_option_id"] == "skill_first"
    assert result["options"][0]["privacy"] == "local_media_with_private_descript_audio_egress"


def test_start_status_packet_and_cancel_use_public_job_states(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)

    started = service.edit_start(str(source), format="youtube")
    run_dir = Path(started["run_dir"])
    (run_dir / "editorial-ledger.json").write_text(
        json.dumps(
            {
                "chunks": [{"id": "chunk-001", "start": 0.0, "end": 1.0, "text": "proof"}],
                "candidates": [],
            }
        )
        + "\n"
    )
    status = service.job_status(started["job_id"])
    packet = service.host_packet(started["job_id"])
    cancelled = service.cancel_job(started["job_id"])

    assert status["state"] == "awaiting_host_plan"
    assert packet["schema_version"] == "eddy-host-packet-v3"
    assert packet["source_hashes"]
    assert packet["editorial_ledger"]["chunks"][0]["id"] == "chunk-001"
    assert packet["motion_requirements"]["shorts"]["minimum_animated_beats"] == 2
    assert packet["motion_requirements"]["longs"]["render_host_authored_plan"] is True
    assert packet["quality_profile"]["id"] == "creator_good_v1"
    assert packet["quality_profile"]["captions"]["terminal_punctuation"] == [".", "?", "!"]
    assert packet["requested_host_action"] == "review_every_chunk_and_resolve_every_ledger_item"
    assert cancelled["state"] == "cancelled"


def test_changes_requested_feedback_reopens_completed_job_for_repair(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)
    started = service.edit_start(str(source), format="youtube")
    run_dir = Path(started["run_dir"])
    (run_dir / "final").mkdir()
    (run_dir / "final" / "long-primary.mp4").write_bytes(b"candidate")
    state = json.loads((run_dir / "state.json").read_text())
    state["state"] = "completed"
    (run_dir / "state.json").write_text(json.dumps(state))

    result = service.record_feedback(
        started["job_id"],
        {
            "schema_version": "owner-feedback-v1",
            "job_id": started["job_id"],
            "verdict": "changes_requested",
            "approval_scope": ["long-primary"],
            "summary": "Redact the incidental bystander comment before staging.",
            "issues": [
                {
                    "artifact": "long-primary.mp4",
                    "evidence": "A third-party name, handle, and profane comment are legible.",
                    "category": "deterministic_bug",
                    "scope": "current_run",
                    "desired_correction": "Burn in a hook-scoped privacy mask before Studio Sound.",
                }
            ],
        },
    )

    assert result["status"] == "recorded"
    assert result["job"]["state"] == "awaiting_host_repair"
    assert (run_dir / "quarantine" / "attempt-1" / "long-primary.mp4").exists()


def test_sync_doctor_distinguishes_owner_main_and_stable_channels(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(
        tmp_path / "runs",
        canonical_root=Path(__file__).resolve().parents[1],
        auto_prepare=False,
    )

    result = service.sync_doctor()

    assert result["product"] == "Eddy"
    assert result["owner_channel"] == "main"
    assert result["public_channel"] == "stable_tags"
    assert result["canonical_commit"]
    assert result["owner_plugin"]["version"] == "3.0.0"
