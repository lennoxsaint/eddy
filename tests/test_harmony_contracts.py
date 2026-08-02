from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eddy.capabilities import eddy_capabilities, validate_capabilities
from eddy.correction_pack import (
    CorrectionPackError,
    materialize_correction_pack,
    validate_correction_pack,
)
from eddy.design_contracts import create_contract_bundle
from eddy.cut_boundaries import (
    CutBoundaryError,
    audit_timeline,
    boundary_review_commands,
)
from eddy.plan import EditPlanV3, PlanValidationError
from eddy.professional_proof import (
    GATE_EVALUATORS,
    GATE_METRIC_REQUIREMENTS,
    REQUIRED_PROFESSIONAL_GATES_V2,
    validate_professional_gate_receipt,
    validate_verifier_review,
)
from eddy.project_brief import (
    ProjectFactBriefError,
    materialize_project_fact_brief,
    validate_project_fact_brief,
)
from eddy.quality import resolve_quality_profile
from eddy.runtime import JobManager, JobState
from eddy.service import EddyService
from test_runtime import valid_plan_v35, valid_plan_v36


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v37_plan(route_count: int) -> dict:
    payload = valid_plan_v35()
    payload["schema_version"] = "edit-plan-v3.7"
    payload["contract_bundle"]["schema_version"] = "eddy-contract-bundle-ref-v3"
    payload["project_fact_brief"]["schema_version"] = (
        "eddy-project-fact-brief-ref-v2"
    )
    payload["cut_integrity_plan"].update(
        {
            "schema_version": "eddy-cut-integrity-plan-v2",
            "boundary_manifest_required": True,
            "micro_insert_frames": [1, 6],
            "silent_handle_max_seconds": 0.24,
            "silent_handle_max_dbfs": -40,
            "boundary_frame_window_each_side": 8,
            "boundary_supercut_speed": 0.25,
            "decoder_policy": "fps_mode_passthrough",
            "protected_exception_evidence_required": True,
            "complete_clause_source_check_required": True,
        }
    )
    for route_index in range(4, route_count + 1):
        hook = copy.deepcopy(payload["hooks"][0])
        hook["id"] = f"route-{route_index}"
        hook["rank"] = route_index
        hook["segments"] = [[50.0 + route_index, 80.0 + route_index]]
        payload["hooks"].append(hook)

        beat_ids = []
        for beat_index in range(8):
            beat = copy.deepcopy(payload["motion_beats"][beat_index])
            beat_id = f"route-{route_index}-opening-beat-{beat_index + 1}"
            beat["id"] = beat_id
            beat["hook_id"] = hook["id"]
            beat_ids.append(beat_id)
            payload["motion_beats"].append(beat)
        variant = copy.deepcopy(payload["opening_visual_contract"]["variants"][0])
        variant["variant_id"] = f"opening-{route_index}"
        variant["hook_id"] = hook["id"]
        variant["meaningful_visual_beat_ids"] = beat_ids
        payload["opening_visual_contract"]["variants"].append(variant)

        opening = copy.deepcopy(payload["visual_choreography"]["openings"][0])
        opening["id"] = f"opening-{route_index}"
        opening["hook_id"] = hook["id"]
        opening["ranking_evidence"] = [f"opening-review-{route_index}.json"]
        for scene_index, scene in enumerate(opening["scenes"], start=1):
            scene["id"] = f"route-{route_index}-scene-{scene_index}"
        payload["visual_choreography"]["openings"].append(opening)
    payload["hooks"] = payload["hooks"][:route_count]
    payload["opening_visual_contract"]["variants"] = payload[
        "opening_visual_contract"
    ]["variants"][:route_count]
    payload["visual_choreography"]["openings"] = payload[
        "visual_choreography"
    ]["openings"][:route_count]
    allowed_hooks = {hook["id"] for hook in payload["hooks"]}
    payload["motion_beats"] = [
        beat for beat in payload["motion_beats"] if beat.get("hook_id") in allowed_hooks
    ]
    return payload


@pytest.mark.parametrize("route_count", [3, 6])
def test_v37_accepts_three_to_six_routes_with_one_shared_body(route_count: int) -> None:
    plan = EditPlanV3.from_dict(_v37_plan(route_count))

    assert plan.schema_version == "edit-plan-v3.7"
    assert len(plan.hooks) == route_count
    assert plan.opening_blueprint_delivery is None
    assert plan.body.keep


@pytest.mark.parametrize("route_count", [2, 7])
def test_v37_rejects_route_counts_outside_contract(route_count: int) -> None:
    with pytest.raises(PlanValidationError, match="long_routes_count_must_be_3_to_6"):
        EditPlanV3.from_dict(_v37_plan(route_count))


def test_v37_rejects_duplicate_route_ids() -> None:
    payload = _v37_plan(6)
    payload["hooks"][5]["id"] = payload["hooks"][4]["id"]
    with pytest.raises(PlanValidationError, match="hook_ids_must_be_unique"):
        EditPlanV3.from_dict(payload)


def test_v37_accepts_explicit_blueprint_v2_without_inferring_it_from_route_count() -> None:
    payload = valid_plan_v36()
    payload["schema_version"] = "edit-plan-v3.7"
    payload["contract_bundle"]["schema_version"] = "eddy-contract-bundle-ref-v3"
    payload["project_fact_brief"]["schema_version"] = (
        "eddy-project-fact-brief-ref-v2"
    )
    payload["opening_visual_contract"]["delivery_target_schema"] = "edit-plan-v3.7"
    payload["opening_blueprint_delivery"]["schema_version"] = (
        "eddy-opening-blueprint-delivery-v2"
    )
    payload["cut_integrity_plan"].update(
        {
            "schema_version": "eddy-cut-integrity-plan-v2",
            "boundary_manifest_required": True,
            "micro_insert_frames": [1, 6],
            "silent_handle_max_seconds": 0.24,
            "silent_handle_max_dbfs": -40,
            "boundary_frame_window_each_side": 8,
            "boundary_supercut_speed": 0.25,
            "decoder_policy": "fps_mode_passthrough",
            "protected_exception_evidence_required": True,
            "complete_clause_source_check_required": True,
        }
    )

    plan = EditPlanV3.from_dict(payload)
    assert plan.opening_blueprint_delivery["schema_version"] == (
        "eddy-opening-blueprint-delivery-v2"
    )


def test_project_fact_brief_v2_accepts_six_and_rejects_duplicate_routes() -> None:
    routes = [
        {
            "id": f"route-{index}",
            "label": f"Route {index}",
            "rank": index,
            "required": True,
            "primary": index == 5,
        }
        for index in range(1, 7)
    ]
    brief = {
        "schema_version": "eddy-project-fact-brief-v2",
        "project_id": "synthetic-six-route",
        "status": "verified",
        "people": [],
        "facts": [],
        "brand": {"tokens": {}, "asset_refs": []},
        "ui_surfaces": [],
        "output": {"long_captions": False, "long_routes": routes},
        "audio": {"studio_sound_required": True, "source_audio_roles": []},
        "protected_moments": [],
    }
    assert len(validate_project_fact_brief(brief)["output"]["long_routes"]) == 6

    duplicate = copy.deepcopy(brief)
    duplicate["output"]["long_routes"][5]["id"] = "route-5"
    with pytest.raises(ProjectFactBriefError, match="long_route_ids_duplicated"):
        validate_project_fact_brief(duplicate)


def test_correction_pack_requires_traceable_single_owner_rows() -> None:
    pack = {
        "schema_version": "eddy-correction-pack-v1",
        "project_id": "synthetic-project",
        "public_safe": True,
        "unsafe_ledger_bodies_reopened": False,
        "corrections": [
            {
                "id": "CUT-001",
                "target": "all-cuts",
                "owning_layer": "eddy_core",
                "source_ref": "receipt:public-safe-v2",
                "approximate_timecode": "00:07",
                "acceptance_probe": "boundary audit has no drop candidates",
                "evidence_schema": "professional-gate-evidence-v2",
                "supersedes": [],
                "status": "active",
            }
        ],
    }
    assert validate_correction_pack(pack)["corrections"][0]["owning_layer"] == "eddy_core"

    unsafe = {**pack, "unsafe_ledger_bodies_reopened": True}
    with pytest.raises(CorrectionPackError, match="unsafe_ledger_boundary_invalid"):
        validate_correction_pack(unsafe)


def test_correction_pack_materializes_atomically_and_rejects_ambiguous_targets(
    tmp_path: Path,
) -> None:
    ref = materialize_correction_pack(
        tmp_path,
        project_id="synthetic-project",
    )
    assert ref["schema_version"] == "eddy-correction-pack-ref-v1"
    assert (tmp_path / ref["ref"]).is_file()

    supplied_path = tmp_path / "supplied-correction-pack.json"
    supplied_path.write_text((tmp_path / ref["ref"]).read_text())
    supplied_ref = materialize_correction_pack(
        tmp_path / "supplied-run",
        project_id="synthetic-project",
        explicit=supplied_path,
    )
    assert supplied_ref["provenance"]["kind"] == "supplied_file"
    assert supplied_ref["provenance"]["source_sha256"] == _sha256(supplied_path)
    inline_ref = materialize_correction_pack(
        tmp_path / "inline-run",
        project_id="synthetic-project",
        explicit=json.loads(supplied_path.read_text()),
    )
    assert inline_ref["provenance"]["kind"] == "inline"
    with pytest.raises(CorrectionPackError, match="correction_pack_missing"):
        materialize_correction_pack(
            tmp_path / "missing-run",
            project_id="synthetic-project",
            explicit=tmp_path / "missing.json",
        )
    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("{")
    with pytest.raises(CorrectionPackError, match="correction_pack_invalid"):
        materialize_correction_pack(
            tmp_path / "corrupt-run",
            project_id="synthetic-project",
            explicit=corrupt_path,
        )

    base = json.loads((tmp_path / ref["ref"]).read_text())
    row = {
        "id": "C-1",
        "target": "opening",
        "owning_layer": "owner_profile",
        "source_ref": "receipt:synthetic",
        "acceptance_probe": "owner profile gate",
        "evidence_schema": "professional-gate-evidence-v2",
        "supersedes": [],
        "status": "active",
    }
    base["corrections"] = [row, {**row, "id": "C-2"}]
    with pytest.raises(CorrectionPackError, match="active_target_ambiguous"):
        validate_correction_pack(base)


def test_project_fact_brief_v2_binds_declared_source_audio_roles(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"synthetic")
    brief = {
        "schema_version": "eddy-project-fact-brief-v2",
        "project_id": "audio-roles",
        "status": "verified",
        "people": [],
        "facts": [],
        "brand": {"tokens": {}, "asset_refs": []},
        "ui_surfaces": [],
        "output": {
            "long_captions": False,
            "long_routes": [
                {"id": "a", "label": "A", "rank": 1, "required": True, "primary": True},
                {"id": "b", "label": "B", "rank": 2, "required": True, "primary": False},
                {"id": "c", "label": "C", "rank": 3, "required": True, "primary": False},
            ],
        },
        "audio": {
            "studio_sound_required": True,
            "source_audio_roles": [
                {
                    "id": "voice-mode",
                    "role": "system_response",
                    "source_ref": "camera.mp4",
                    "required_intervals": [[10.0, 12.0]],
                }
            ],
        },
        "protected_moments": [],
    }
    ref = materialize_project_fact_brief(
        tmp_path / "run",
        source=source,
        explicit=brief,
    )
    assert ref["schema_version"] == "eddy-project-fact-brief-ref-v2"

    brief_path = tmp_path / "supplied-project-fact-brief.json"
    brief_path.write_text(json.dumps(brief) + "\n")
    supplied_ref = materialize_project_fact_brief(
        tmp_path / "supplied-run",
        source=source,
        explicit=brief_path,
    )
    assert supplied_ref["provenance"]["kind"] == "supplied_file"

    bad = copy.deepcopy(brief)
    bad["audio"]["source_audio_roles"][0]["role"] = "synthesized"
    with pytest.raises(ProjectFactBriefError, match="source_audio_role_invalid"):
        validate_project_fact_brief(bad)


def test_micro_insert_and_silent_handle_fail_until_timeline_is_repaired() -> None:
    manifest = {
        "schema_version": "eddy-cut-boundary-manifest-v1",
        "fps": 25,
        "segments": [
            {"id": "a", "source_id": "camera-a", "timeline_start": 0, "timeline_end": 1, "rms_dbfs": -18},
            {"id": "stray", "source_id": "camera-z", "timeline_start": 1, "timeline_end": 1.12, "rms_dbfs": -70},
            {"id": "b", "source_id": "camera-b", "timeline_start": 1.12, "timeline_end": 2, "rms_dbfs": -18},
        ],
    }
    failed = audit_timeline(manifest)
    assert failed["pass"] is False
    assert failed["drop_segment_ids"] == ["stray"]
    assert failed["candidates"][0]["pattern"] == "third_shot"

    repaired = copy.deepcopy(manifest)
    repaired["segments"].pop(1)
    passed = audit_timeline(repaired)
    assert passed["pass"] is True
    assert passed["drop_segment_ids"] == []


def test_boundary_review_commands_use_passthrough_frames_and_quarter_speed(
    tmp_path: Path,
) -> None:
    audit = audit_timeline(
        {
            "schema_version": "eddy-cut-boundary-manifest-v1",
            "fps": 25,
            "segments": [
                {"id": "a", "source_id": "camera-a", "timeline_start": 0, "timeline_end": 1, "rms_dbfs": -18},
                {"id": "b", "source_id": "camera-b", "timeline_start": 1, "timeline_end": 2, "rms_dbfs": -18},
            ],
        }
    )
    media = tmp_path / "synthetic.mp4"
    commands, outputs = boundary_review_commands(media, audit, tmp_path / "review")

    assert "passthrough" in commands[0]
    assert any("tile=17x1" in part for part in commands[0])
    filter_index = commands[-1].index("-filter_complex") + 1
    assert "setpts=4*(PTS-STARTPTS)" in commands[-1][filter_index]
    assert outputs[-1] == "boundary-supercut-0.25x.mp4"


def test_boundary_review_renders_synthetic_strip_and_supercut(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg unavailable")
    media = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=25:duration=3",
            "-pix_fmt",
            "yuv420p",
            str(media),
        ],
        check=True,
        capture_output=True,
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "eddy-cut-boundary-manifest-v1",
                "fps": 25,
                "segments": [
                    {"id": "a", "source_id": "camera-a", "timeline_start": 0, "timeline_end": 1, "rms_dbfs": -18},
                    {"id": "b", "source_id": "camera-b", "timeline_start": 1, "timeline_end": 2, "rms_dbfs": -18},
                    {"id": "c", "source_id": "camera-c", "timeline_start": 2, "timeline_end": 3, "rms_dbfs": -18},
                ],
            }
        )
        + "\n"
    )
    review = tmp_path / "review"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "boundary_audit.py"),
            str(manifest),
            "--output",
            str(tmp_path / "audit.json"),
            "--media",
            str(media),
            "--review-dir",
            str(review),
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert (review / "frame-strips" / "boundary-0001.png").stat().st_size > 0
    assert (review / "boundary-supercut-0.25x.mp4").stat().st_size > 0
    receipt = json.loads((review / "boundary-review-receipt.json").read_text())
    assert receipt["decoder_policy"] == "fps_mode_passthrough"


def test_protected_micro_insert_requires_purpose_specific_evidence() -> None:
    manifest = {
        "schema_version": "eddy-cut-boundary-manifest-v1",
        "fps": 25,
        "segments": [
            {"id": "a", "source_id": "camera-a", "timeline_start": 0, "timeline_end": 1, "rms_dbfs": -18},
            {
                "id": "insert",
                "source_id": "proof-card",
                "timeline_start": 1,
                "timeline_end": 1.12,
                "rms_dbfs": -70,
                "protected": True,
                "protected_reason": "Three-frame factual proof flash",
                "protected_evidence_ref": "evidence/insert-purpose.json",
                "protected_evidence_sha256": "a" * 64,
                "protected_evidence_purpose_specific": True,
                "protected_evidence_self_attested": False,
            },
            {"id": "b", "source_id": "camera-b", "timeline_start": 1.12, "timeline_end": 2, "rms_dbfs": -18},
        ],
    }
    assert audit_timeline(manifest)["pass"] is True

    manifest["segments"][1].pop("protected_evidence_ref")
    with pytest.raises(ValueError, match="protected_evidence_required"):
        audit_timeline(manifest)


@pytest.mark.parametrize(
    ("manifest", "blocker"),
    [
        ({}, "manifest_schema_invalid"),
        ({"schema_version": "eddy-cut-boundary-manifest-v1", "fps": 0}, "fps_invalid"),
        (
            {"schema_version": "eddy-cut-boundary-manifest-v1", "fps": 25, "segments": []},
            "segments_required",
        ),
    ],
)
def test_cut_boundary_manifest_fails_closed(manifest: dict, blocker: str) -> None:
    with pytest.raises(CutBoundaryError, match=blocker):
        audit_timeline(manifest)


@pytest.mark.parametrize(
    ("segment", "blocker"),
    [
        ("bad", "segment_invalid"),
        ({"id": "x"}, "source_id_required"),
        (
            {
                "id": "x",
                "source_id": "camera",
                "timeline_start": 1,
                "timeline_end": 0,
                "rms_dbfs": -20,
            },
            "segment_range_invalid",
        ),
        (
            {
                "id": "x",
                "source_id": "camera",
                "timeline_start": 0,
                "timeline_end": 1,
                "rms_dbfs": -20,
                "protected": "yes",
            },
            "protected_invalid",
        ),
    ],
)
def test_cut_boundary_segments_fail_closed(segment: object, blocker: str) -> None:
    manifest = {
        "schema_version": "eddy-cut-boundary-manifest-v1",
        "fps": 25,
        "segments": [segment],
    }
    with pytest.raises(CutBoundaryError, match=blocker):
        audit_timeline(manifest)


def _gate_receipt(attempt: Path) -> dict:
    gates = {}
    for gate_id in sorted(REQUIRED_PROFESSIONAL_GATES_V2):
        artifact = attempt / "artifacts" / f"{gate_id}.txt"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f"synthetic measurement for {gate_id}\n")
        evidence = attempt / "gates" / f"{gate_id}.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        requirement = GATE_METRIC_REQUIREMENTS[gate_id]
        metrics = {
            "evaluated_by": GATE_EVALUATORS[gate_id],
            "sample_count": 1,
            "failures": 0,
        }
        for key, expected in requirement.items():
            if key in {"evaluated_by", "sample_count_min", "failures"}:
                continue
            if key in {"long_route_count_min", "long_route_count_max"}:
                metrics["long_route_count"] = 3
            else:
                metrics[key] = expected
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": "professional-gate-evidence-v2",
                    "gate_id": gate_id,
                    "evaluator_id": GATE_EVALUATORS[gate_id],
                    "status": "pass",
                    "self_attested": False,
                    "metrics": metrics,
                    "artifacts": [
                        {
                            "ref": artifact.relative_to(attempt).as_posix(),
                            "sha256": _sha256(artifact),
                            "role": "purpose_specific_probe",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n"
        )
        gates[gate_id] = {
            "passed": True,
            "evidence": [
                {
                    "type": "measurement",
                    "ref": evidence.relative_to(attempt).as_posix(),
                    "sha256": _sha256(evidence),
                }
            ],
        }
    return {"schema_version": "professional-gate-evidence-v2", "gates": gates}


def test_gate_specific_evidence_passes_and_generic_reuse_fails(tmp_path: Path) -> None:
    receipt = _gate_receipt(tmp_path)
    assert all(validate_professional_gate_receipt(tmp_path, receipt).values())

    first, second = sorted(REQUIRED_PROFESSIONAL_GATES_V2)[:2]
    receipt["gates"][second]["evidence"] = copy.deepcopy(
        receipt["gates"][first]["evidence"]
    )
    with pytest.raises(ValueError, match="evidence_payload_invalid"):
        validate_professional_gate_receipt(tmp_path, receipt)


def test_verifier_v2_requires_every_output_and_clean_boundary_review(tmp_path: Path) -> None:
    paths = [
        *(tmp_path / f"long-{index}.mp4" for index in range(1, 4)),
        *(tmp_path / "shorts" / f"short-{index}.mp4" for index in range(1, 4)),
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic-output")
    supercut = tmp_path / "boundary-supercut.mp4"
    supercut.write_bytes(b"synthetic-supercut")
    decisions = tmp_path / "cut-boundary-audit.json"
    decisions.write_text(
        json.dumps(
            {
                "schema_version": "eddy-cut-boundary-audit-v1",
                "pass": True,
                "unresolved": [],
                "drop_segment_ids": [],
            }
        )
        + "\n"
    )
    review = {
        "schema_version": "verifier-review-v2",
        "authority": "independent_no_edit_context",
        "edit_authority": False,
        "promotion_recommendation": "objective_green",
        "outputs": [
            {
                "ref": path.relative_to(tmp_path).as_posix(),
                "sha256": _sha256(path),
                "duration_seconds": 1,
                "watched_seconds": 1,
                "listened_seconds": 1,
                "full_watch": True,
                "full_listen": True,
                "defects": [],
            }
            for path in paths
        ],
        "boundary_review": {
            "all_boundaries_reviewed": True,
            "playback_speed": 0.25,
            "frame_window_each_side": 8,
            "decoder_policy": "fps_mode_passthrough",
            "supercut_ref": supercut.name,
            "supercut_sha256": _sha256(supercut),
            "candidate_decisions_ref": decisions.name,
            "candidate_decisions_sha256": _sha256(decisions),
        },
    }
    assert validate_verifier_review(tmp_path, review)["output_count"] == 6

    review["boundary_review"]["playback_speed"] = 1
    with pytest.raises(ValueError, match="boundary_review_contract_invalid"):
        validate_verifier_review(tmp_path, review)


def test_editor_self_attestation_cannot_clear_detected_gate(tmp_path: Path) -> None:
    receipt = _gate_receipt(tmp_path)
    gate_id = sorted(REQUIRED_PROFESSIONAL_GATES_V2)[0]
    ref = receipt["gates"][gate_id]["evidence"][0]["ref"]
    evidence_path = tmp_path / ref
    payload = json.loads(evidence_path.read_text())
    payload["self_attested"] = True
    evidence_path.write_text(json.dumps(payload) + "\n")
    receipt["gates"][gate_id]["evidence"][0]["sha256"] = _sha256(evidence_path)
    with pytest.raises(ValueError, match="evidence_payload_invalid"):
        validate_professional_gate_receipt(tmp_path, receipt)


@pytest.mark.parametrize(
    ("gate_id", "metric", "wrong_value"),
    [
        ("factual_bindings", "rendered_fact_mismatch_count", 1),
        ("caption_override_accuracy", "override_mismatch_count", 1),
        ("caption_override_accuracy", "future_word_visible_frames", 2),
        ("complete_clause_recovery", "clipped_clause_count", 1),
        ("readable_screen_context", "cropped_critical_region_count", 1),
    ],
)
def test_specific_objective_defects_fail_their_own_gate(
    tmp_path: Path,
    gate_id: str,
    metric: str,
    wrong_value: object,
) -> None:
    receipt = _gate_receipt(tmp_path)
    evidence = receipt["gates"][gate_id]["evidence"][0]
    path = tmp_path / evidence["ref"]
    payload = json.loads(path.read_text())
    payload["metrics"][metric] = wrong_value
    path.write_text(json.dumps(payload) + "\n")
    evidence["sha256"] = _sha256(path)
    with pytest.raises(ValueError, match="professional_gate_metrics_invalid"):
        validate_professional_gate_receipt(tmp_path, receipt)


def test_capability_handshake_declares_route_and_evidence_contracts() -> None:
    capabilities = validate_capabilities(eddy_capabilities(ROOT))
    assert capabilities["preferred_edit_plan_schema"] == "edit-plan-v3.7"
    assert capabilities["long_routes"] == {"default": 3, "minimum": 3, "maximum": 6}
    assert capabilities["professional_gates"]["generic_evidence_reuse_allowed"] is False
    broken = {**capabilities, "preferred_edit_plan_schema": "edit-plan-v9"}
    with pytest.raises(ValueError, match="preferred_schema_unsupported"):
        validate_capabilities(broken)
    with pytest.raises(ValueError, match="capabilities_schema_invalid"):
        validate_capabilities({})
    with pytest.raises(ValueError, match="long_routes_invalid"):
        validate_capabilities({**capabilities, "long_routes": {"default": 2}})
    broken_gates = copy.deepcopy(capabilities)
    broken_gates["professional_gates"]["self_attested_clearance_allowed"] = True
    with pytest.raises(ValueError, match="professional_gates_invalid"):
        validate_capabilities(broken_gates)


def test_v3_owner_profile_emits_v33_host_packet_with_six_routes(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"synthetic-media")
    routes = [
        {
            "id": f"route-{index}",
            "label": f"Route {index}",
            "rank": index,
            "required": True,
            "primary": index == 5,
        }
        for index in range(1, 7)
    ]
    brief = {
        "schema_version": "eddy-project-fact-brief-v2",
        "project_id": "synthetic-host-packet",
        "status": "verified",
        "people": [],
        "facts": [],
        "brand": {"tokens": {}, "asset_refs": []},
        "ui_surfaces": [],
        "output": {"long_captions": False, "long_routes": routes},
        "audio": {"studio_sound_required": True, "source_audio_roles": []},
        "protected_moments": [],
    }
    service = EddyService(tmp_path / "runs", canonical_root=ROOT, auto_prepare=False)
    started = service.edit_start(
        str(source),
        profile_id="lennox-professional-youtube-v3",
        project_brief=brief,
    )
    packet = service.host_packet(started["job_id"])

    assert packet["schema_version"] == "eddy-host-packet-v3.3"
    assert packet["edit_plan_schema"] == "edit-plan-v3.7"
    assert packet["contract_bundle"]["schema_version"] == "eddy-contract-bundle-ref-v3"
    assert packet["motion_requirements"]["visual_choreography"]["opening_timelines"] == 6
    assert packet["requirements"]["opening_blueprint_delivery"]["required"] is False


def test_direct_v3_bundle_derives_an_empty_correction_pack(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"synthetic")
    run = tmp_path / "run"
    run.mkdir()
    (run / "source-lock.json").write_text(
        json.dumps({"before": {"camera.mp4": "a" * 64}, "snapshot": {}, "after": None})
        + "\n"
    )
    profile, profile_path = resolve_quality_profile(
        ROOT,
        explicit_profile_id="lennox-professional-youtube-v3",
        owner_state_path=tmp_path / "missing-owner.json",
    )
    bundle_ref = create_contract_bundle(
        run,
        source=source,
        canonical_root=ROOT,
        profile=profile,
        profile_path=profile_path,
        source_hashes={"camera.mp4": "a" * 64},
        hyperframes_root=tmp_path / "missing-hyperframes",
    )
    bundle = json.loads((run / bundle_ref["ref"]).read_text())
    assert bundle["schema_version"] == "eddy-contract-bundle-v3"
    assert bundle["correction_pack"]["provenance"]["kind"] == "derived_empty"


def test_v37_third_failed_attempt_blocks_with_matching_verification_receipt(
    tmp_path: Path,
) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"synthetic")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    (job.run_dir / "edit-plan.json").write_text(
        json.dumps(
            {
                "schema_version": "edit-plan-v3.7",
                "hooks": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            }
        )
        + "\n"
    )
    attempt = job.run_dir / "work" / "attempt-3"
    attempt.mkdir(parents=True)
    (attempt / "partial.txt").write_text("synthetic partial\n")

    result = manager.record_verification(
        job.id,
        attempt=attempt,
        gates={},
        blockers=["cut_boundary_integrity_failed"],
    )

    expected = "technical_blocker:repair_loop_limit_reached"
    assert result.state is JobState.BLOCKED
    assert expected in json.loads((job.run_dir / "verification.json").read_text())[
        "blockers"
    ]
    assert expected in json.loads((job.run_dir / "repair-packet.json").read_text())[
        "blockers"
    ]
