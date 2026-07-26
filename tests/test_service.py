import json
from pathlib import Path

from eddy.service import EddyService
from test_runtime import valid_plan_v32, valid_plan_v33


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
    assert packet["schema_version"] == "eddy-host-packet-v3.1"
    assert packet["source_hashes"]
    assert packet["editorial_ledger"]["chunks"][0]["id"] == "chunk-001"
    assert packet["motion_requirements"]["shorts"]["minimum_animated_beats"] == 2
    assert packet["motion_requirements"]["longs"]["render_host_authored_plan"] is True
    assert packet["motion_requirements"]["longs"]["opening_proof_trailer"]["variants"] == 3
    assert packet["motion_requirements"]["longs"]["adaptive_cadence"]["hard_max_seconds"] == 12
    assert packet["motion_requirements"]["visual_choreography"]["opening_timelines"] == 3
    assert "speaker_edge_right" in packet["motion_requirements"]["visual_choreography"]["layouts"]
    assert packet["edit_plan_schema"] == "edit-plan-v3.4"
    assert packet["accepted_edit_plan_schemas"] == [
        "edit-plan-v3",
        "edit-plan-v3.1",
        "edit-plan-v3.2",
        "edit-plan-v3.3",
        "edit-plan-v3.4",
    ]
    assert packet["requirements"]["body_structure_contract"]["schema_version"] == "eddy-body-structure-v1"
    assert packet["requirements"]["body_structure_contract"]["section_count"] == [3, 5]
    assert packet["requirements"]["body_structure_contract"]["major_order_authority"] == "sage_locked_eddy_may_not_reorder"
    assert Path(packet["frame_contract"]["path"]).name == "frame.md"
    assert Path(packet["design_contracts"]["short_frame"]["path"]).as_posix().endswith(
        "shorts/frame.md"
    )
    assert Path(packet["design_contracts"]["design"]["path"]).name == "design.md"
    assert packet["contract_bundle"]["sha256"]
    assert packet["quality_profile"]["id"] == "creator_good_v1"
    assert packet["quality_profile"]["captions"]["terminal_punctuation"] == [".", "?", "!"]
    assert packet["requested_host_action"] == "review_every_chunk_and_resolve_every_ledger_item"
    assert cancelled["state"] == "cancelled"


def test_explicit_lennox_profile_creates_portable_contract_bundle(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(
        tmp_path / "runs",
        canonical_root=Path(__file__).resolve().parents[1],
        auto_prepare=False,
    )

    started = service.edit_start(
        str(source),
        profile_id="lennox-professional-youtube-v1",
    )
    packet = service.host_packet(started["job_id"])
    bundle = json.loads(Path(packet["contract_bundle"]["path"]).read_text())

    assert packet["quality_profile"]["schema_version"] == "eddy-quality-profile-v2"
    assert packet["quality_profile"]["id"] == "lennox-professional-youtube-v1"
    assert bundle["hyperframes"]["version"] == "0.7.3"
    assert bundle["profile"]["ref"] == "contracts/quality/profile.json"
    assert len(bundle["hyperframes"]["references"]) == 4
    assert Path(started["run_dir"], "design.md").is_file()
    assert Path(started["run_dir"], "frame.md").is_file()
    assert Path(started["run_dir"], "shorts", "frame.md").is_file()


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


def _v32_for_started_job(service: EddyService, started: dict) -> dict:
    packet = service.host_packet(started["job_id"])
    payload = valid_plan_v32()
    payload["source_hashes"] = packet["source_hashes"]
    payload["frame_contract"] = {
        "schema_version": "eddy-project-frame-v1",
        "ref": packet["frame_contract"]["ref"],
        "sha256": packet["frame_contract"]["sha256"],
    }
    return payload


def _v33_for_started_job(service: EddyService, started: dict) -> dict:
    packet = service.host_packet(started["job_id"])
    payload = valid_plan_v33()
    payload["source_hashes"] = packet["source_hashes"]
    payload["frame_contract"] = {
        "schema_version": "eddy-project-frame-v1",
        "ref": packet["frame_contract"]["ref"],
        "sha256": packet["frame_contract"]["sha256"],
    }
    return payload


def test_v32_host_submit_auto_selects_clear_opening_leader(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)
    started = service.edit_start(str(source))

    result = service.host_submit(started["job_id"], _v32_for_started_job(service, started))

    assert result["state"] == "compiling"
    assert result["opening_selection"]["status"] == "auto_selected"
    selection = json.loads((Path(started["run_dir"]) / "opening-selection.json").read_text())
    assert selection["selected_opening_id"] == "opening-1"


def test_v33_host_submit_preserves_locked_body_contract_and_selects_opening(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)
    started = service.edit_start(str(source))
    payload = _v33_for_started_job(service, started)

    result = service.host_submit(started["job_id"], payload)

    assert result["state"] == "compiling"
    assert result["opening_selection"]["status"] == "auto_selected"
    saved = json.loads((Path(started["run_dir"]) / "edit-plan.json").read_text())
    assert saved["body_structure_contract"] == payload["body_structure_contract"]


def test_v32_close_opening_scores_pause_until_explicit_selection(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)
    started = service.edit_start(str(source))
    payload = _v32_for_started_job(service, started)
    payload["visual_choreography"]["openings"][1]["ranking_signals"] = dict(
        payload["visual_choreography"]["openings"][0]["ranking_signals"]
    )

    submitted = service.host_submit(started["job_id"], payload)
    selected = service.select_opening(
        started["job_id"],
        "opening-2",
        reason="The second treatment makes the proof legible on mobile.",
    )

    assert submitted["state"] == "awaiting_opening_selection"
    assert selected["state"] == "compiling"
    assert selected["opening_selection"]["selected_opening_id"] == "opening-2"
