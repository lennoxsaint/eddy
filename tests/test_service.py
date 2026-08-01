import json
import hashlib
from pathlib import Path

from eddy.service import EddyService, _worker_inspection_command
from test_runtime import valid_plan_v32, valid_plan_v33


def test_edit_options_returns_one_runnable_skill_first_path(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)

    result = service.edit_options(str(source), format="youtube")

    assert result["requires_choice"] is False
    assert result["selected_option_id"] == "skill_first"
    assert result["options"][0]["privacy"] == "local_media_with_private_descript_audio_egress"


def test_worker_inspection_commands_are_platform_specific() -> None:
    assert _worker_inspection_command(123, "posix") == [
        "ps",
        "-p",
        "123",
        "-o",
        "command=",
    ]
    assert _worker_inspection_command(123, "nt") == [
        "powershell",
        "-NoProfile",
        "-Command",
        '(Get-CimInstance Win32_Process -Filter "ProcessId = 123").CommandLine',
    ]


def test_start_status_packet_and_cancel_use_public_job_states(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)

    started = service.edit_start(str(source), format="youtube", profile_id="creator_good_v1")
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
    assert packet["schema_version"] == "eddy-host-packet-v3.2"
    assert packet["source_hashes"]
    assert packet["editorial_ledger"]["chunks"][0]["id"] == "chunk-001"
    assert packet["motion_requirements"]["shorts"]["minimum_animated_beats"] == 2
    assert packet["motion_requirements"]["longs"]["render_host_authored_plan"] is True
    assert packet["motion_requirements"]["longs"]["opening_proof_trailer"]["variants"] == 3
    assert packet["motion_requirements"]["longs"]["adaptive_cadence"]["hard_max_seconds"] == 12
    assert packet["motion_requirements"]["visual_choreography"]["opening_timelines"] == 3
    assert "speaker_edge_right" in packet["motion_requirements"]["visual_choreography"]["layouts"]
    assert "speaker_close" in packet["motion_requirements"]["visual_choreography"]["layouts"]
    assert "speaker_tight" in packet["motion_requirements"]["visual_choreography"]["layouts"]
    assert packet["edit_plan_schema"] == "edit-plan-v3.5"
    assert packet["opening_edit_blueprint"] is None
    assert packet["requirements"]["opening_blueprint_delivery"]["required"] is False
    assert packet["accepted_edit_plan_schemas"] == [
        "edit-plan-v3",
        "edit-plan-v3.1",
        "edit-plan-v3.2",
        "edit-plan-v3.3",
        "edit-plan-v3.4",
        "edit-plan-v3.5",
        "edit-plan-v3.6",
    ]
    assert packet["motion_requirements"]["longs"]["opening_edit_blueprint"] == {
        "contract_version": "2.0",
        "delivery_schema": "eddy-opening-blueprint-delivery-v1",
        "function_policy": "function_locked_style_flexible",
        "opening_window_seconds": [0, 30],
        "bridge_window_seconds": [30, 60],
        "every_delivered_scene_requires_mapping": True,
        "deviation_receipt_required": True,
    }
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


def test_v7_project_blueprint_is_snapshotted_and_selects_v36(tmp_path: Path) -> None:
    project = tmp_path / "project"
    source = project / "source" / "raw"
    source.mkdir(parents=True)
    (source / "camera.mp4").write_bytes(b"raw")
    review = project / "pre-production" / "review"
    review.mkdir(parents=True)
    mechanics = review / "opening-mechanics-library.json"
    mechanics.write_text(
        '{"schema_version":"1.0","gate_status":"human_confirmed"}\n'
    )

    mechanics_hash = hashlib.sha256(mechanics.read_bytes()).hexdigest()
    mechanic_ids = ["proof-first-frame"]

    def planned_scene(scene_id: str, start: float, end: float) -> dict:
        return {
            "beat_id": scene_id,
            "start_second": start,
            "end_second": end,
            "mechanic_ids": mechanic_ids,
            "semantic_job": "change the viewer evidence state",
            "spoken_anchor": "exact source phrase",
            "asset_job": "show owned proof",
            "proof_job": "make the claim inspectable",
            "audio_job": "support without masking speech",
            "motion_job": "move evidence into focus",
            "cut_job": "cut when the evidence state changes",
            "intended_viewer_state": "understands the claim and next question",
            "fallback": "hard cut to owned proof",
        }

    variants = []
    for variant_index, hook_id in enumerate(("proof", "speed", "cost")):
        variants.append(
            {
                "variant_id": f"opening-{variant_index + 1}",
                "hook_id": hook_id,
                "style_policy": "function_locked_style_flexible",
                "opening_edit_blueprint": {
                    "window_seconds": [0, 30],
                    "beats": [
                        planned_scene(
                            f"{hook_id}-beat-{index + 1}",
                            index * 3.5,
                            index * 3.5 + 3.4,
                        )
                        for index in range(8)
                    ],
                },
                "bridge_30_60": {
                    "window_seconds": [30, 60],
                    "scenes": [
                        planned_scene(
                            f"{hook_id}-bridge-{index + 1}",
                            30 + index * 10,
                            40 + index * 10,
                        )
                        for index in range(3)
                    ],
                },
                "thresholds": {
                    "money_shot_by_second": 3,
                    "real_proof_by_second": 10,
                    "stakes_by_second": 30,
                    "meaningful_visual_beats_min": 8,
                    "meaningful_visual_beats_soft_max": 12,
                },
                "muted_preview": {"status": "pass"},
                "mobile_preview": {"status": "pass"},
                "taste_review": {"status": "pass"},
            }
        )
    blueprint = {
        "schema_version": "2.0",
        "contract_kind": "opening_edit_blueprint",
        "profile_version": 7,
        "delivery_target_schema": "edit-plan-v3.6",
        "opening_contact_sheet_ref": "pre-production/visuals/openings/contact-sheet.png",
        "benchmark_binding": {
            "benchmark_revision": "omb-v1-2026-07-30",
            "mechanics_library_id": "opening-mechanics-library-v1",
            "mechanics_library_ref": (
                "pre-production/review/opening-mechanics-library.json"
            ),
            "mechanics_library_sha256": mechanics_hash,
            "evidence_authority": "observed_cross_creator_not_causal",
            "selected_mechanic_ids": mechanic_ids,
        },
        "variants": variants,
    }
    (review / "opening-edit-blueprint.json").write_text(
        json.dumps(blueprint) + "\n"
    )
    service = EddyService(tmp_path / "runs", auto_prepare=False)

    started = service.edit_start(str(source), profile_id="creator_good_v1")
    packet = service.host_packet(started["job_id"])

    assert packet["edit_plan_schema"] == "edit-plan-v3.6"
    assert packet["opening_edit_blueprint"]["schema_version"] == "2.0"
    assert packet["requirements"]["opening_blueprint_delivery"]["required"] is True
    snapshotted = (
        Path(started["run_dir"])
        / "pre-production"
        / "review"
        / "opening-edit-blueprint.json"
    )
    assert snapshotted.read_bytes() == (
        review / "opening-edit-blueprint.json"
    ).read_bytes()


def test_v7_project_blueprint_rejects_unconfirmed_mechanics_library(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    source = project / "source"
    source.mkdir(parents=True)
    (source / "camera.mp4").write_bytes(b"raw")
    review = project / "pre-production" / "review"
    review.mkdir(parents=True)
    mechanics = review / "opening-mechanics-library.json"
    mechanics.write_text(
        '{"schema_version":"1.0","gate_status":"machine_reviewed"}\n'
    )
    blueprint = {
        "benchmark_binding": {
            "mechanics_library_ref": (
                "pre-production/review/opening-mechanics-library.json"
            ),
            "mechanics_library_sha256": hashlib.sha256(
                mechanics.read_bytes()
            ).hexdigest(),
        }
    }
    (review / "opening-edit-blueprint.json").write_text(
        json.dumps(blueprint) + "\n"
    )
    service = EddyService(tmp_path / "runs", auto_prepare=False)

    import pytest

    with pytest.raises(
        ValueError,
        match="opening_blueprint_mechanics_library_not_human_confirmed",
    ):
        service.edit_start(str(source), profile_id="creator_good_v1")


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
