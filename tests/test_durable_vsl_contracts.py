from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from eddy.design_contracts import create_contract_bundle
from eddy.feedback import record_owner_feedback
from eddy.media_integrity import (
    content_addressed_cache_key,
    motion_segment_coverage_verdict,
    progressive_caption_verdict,
    sequence_search_parity,
    shared_body_hash_verdict,
    shot_entry_latency_verdict,
    word_edge_protection_verdict,
)
from eddy.professional_proof import (
    REQUIRED_PROFESSIONAL_GATES,
    validate_open_items,
    validate_professional_gate_receipt,
    validate_verifier_review,
)
from eddy.project_brief import ProjectFactBriefError, materialize_project_fact_brief
from eddy.quality import resolve_quality_profile
from eddy.runtime import JobState, V35_REQUIRED_FINAL_GATES
from eddy.service import EddyService
from test_runtime import valid_plan_v35


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deliverables(attempt: Path) -> list[Path]:
    outputs = [
        attempt / "long-primary.mp4",
        attempt / "long-alternate-proof.mp4",
        attempt / "long-alternate-stakes.mp4",
        attempt / "shorts" / "short-01.mp4",
        attempt / "shorts" / "short-02.mp4",
        attempt / "shorts" / "short-03.mp4",
    ]
    for index, path in enumerate(outputs, start=1):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"output-{index}".encode())
    return outputs


def _evidence_item(attempt: Path, ref: str) -> dict[str, str]:
    path = attempt / ref
    return {
        "type": "measurement",
        "ref": ref,
        "sha256": _sha256(path),
    }


def test_project_fact_brief_is_restrictive_and_hash_bound(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw")
    explicit = tmp_path / "brief.json"
    explicit.write_text(
        json.dumps(
            {
                "schema_version": "eddy-project-fact-brief-v1",
                "project_id": "generic-vsl",
                "status": "verified",
                "people": [
                    {
                        "id": "speaker-1",
                        "display_name": "Verified Speaker",
                        "source_refs": ["brief:people/speaker-1"],
                    }
                ],
                "facts": [
                    {
                        "id": "offer-url",
                        "value": "https://example.test/offer",
                        "required": True,
                        "source_refs": ["brief:offer"],
                    }
                ],
                "brand": {
                    "tokens": {
                        "background": "#111827",
                        "foreground": "#F9FAFB",
                        "accent": "#F97316",
                    },
                    "asset_refs": [],
                },
                "ui_surfaces": [
                    {
                        "id": "offer-page",
                        "evidence_kind": "reconstructed",
                        "source_refs": ["brief:offer"],
                        "factual_bindings": ["offer-url"],
                    }
                ],
                "output": {"long_captions": False, "runtime_target_seconds": 300},
                "audio": {"studio_sound_required": True},
                "protected_moments": [],
            }
        )
    )

    result = materialize_project_fact_brief(
        tmp_path / "run",
        source=source,
        explicit=explicit,
    )

    written = Path(result["path"])
    payload = json.loads(written.read_text())
    assert result["schema_version"] == "eddy-project-fact-brief-ref-v1"
    assert result["sha256"] == _sha256(written)
    assert payload["output"]["long_captions"] is False
    assert payload["ui_surfaces"][0]["evidence_kind"] == "reconstructed"


def test_project_fact_brief_rejects_missing_essential_facts(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    payload = {
        "schema_version": "eddy-project-fact-brief-v1",
        "project_id": "blocked-vsl",
        "status": "verified",
        "people": [],
        "facts": [
            {
                "id": "required-url",
                "value": "",
                "required": True,
                "source_refs": [],
            }
        ],
        "brand": {"tokens": {}, "asset_refs": []},
        "ui_surfaces": [],
        "output": {"long_captions": False},
        "audio": {"studio_sound_required": True},
        "protected_moments": [],
    }

    with pytest.raises(ProjectFactBriefError, match="project_fact_required_missing"):
        materialize_project_fact_brief(
            tmp_path / "run",
            source=source,
            explicit=payload,
        )


def test_lennox_v2_bundle_binds_brief_and_v2_design_contracts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw")
    run = tmp_path / "run"
    run.mkdir()
    (run / "source-lock.json").write_text(
        json.dumps({"before": {"camera.mp4": "a" * 64}, "snapshot": {}, "after": None})
    )
    brief_ref = materialize_project_fact_brief(run, source=source)
    profile, profile_path = resolve_quality_profile(
        ROOT,
        explicit_profile_id="lennox-professional-youtube-v2",
        owner_state_path=tmp_path / "missing-owner.json",
    )

    result = create_contract_bundle(
        run,
        source=source,
        canonical_root=ROOT,
        profile=profile,
        profile_path=profile_path,
        source_hashes={"camera.mp4": "a" * 64},
        project_fact_brief=brief_ref,
        hyperframes_root=tmp_path / "missing-hyperframes",
    )

    bundle = json.loads((run / "contracts" / "contract-bundle.json").read_text())
    assert result["schema_version"] == "eddy-contract-bundle-ref-v2"
    assert bundle["schema_version"] == "eddy-contract-bundle-v2"
    assert bundle["project_fact_brief"]["sha256"] == brief_ref["sha256"]
    assert bundle["profile"]["id"] == "lennox-professional-youtube-v2"
    assert "designed_long_captions: false" in (run / "frame.md").read_text()
    short_frame = (run / "shorts" / "frame.md").read_text()
    assert "speaker_attribution: color_plus_label" in short_frame
    assert "future_words: invisible" in short_frame


def test_professional_gate_receipt_requires_hash_bound_evidence(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    (attempt / "qa").mkdir()
    evidence = attempt / "qa" / "measured.json"
    evidence.write_text('{"status":"pass"}\n')
    item = _evidence_item(attempt, "qa/measured.json")
    payload = {
        "schema_version": "eddy-professional-gates-v1",
        "gates": {
            gate: {"passed": True, "evidence": [item]}
            for gate in sorted(REQUIRED_PROFESSIONAL_GATES)
        },
    }

    result = validate_professional_gate_receipt(attempt, payload)
    assert set(result) == REQUIRED_PROFESSIONAL_GATES
    assert all(result.values())

    stale = json.loads(json.dumps(payload))
    stale["gates"]["content_hash_cache_keys"]["evidence"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="professional_gate_evidence_hash_mismatch"):
        validate_professional_gate_receipt(attempt, stale)


def test_independent_verifier_must_cover_every_final_output(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    outputs = _deliverables(attempt)
    review = {
        "schema_version": "verifier-review-v1",
        "authority": "independent_no_edit_context",
        "edit_authority": False,
        "promotion_recommendation": "objective_green",
        "outputs": [
            {
                "ref": path.relative_to(attempt).as_posix(),
                "sha256": _sha256(path),
                "duration_seconds": 1.0,
                "watched_seconds": 1.0,
                "listened_seconds": 1.0,
                "full_watch": True,
                "full_listen": True,
                "defects": [],
            }
            for path in outputs
        ],
    }

    assert validate_verifier_review(attempt, review)["output_count"] == 6

    self_review = {**review, "edit_authority": True}
    with pytest.raises(ValueError, match="verifier_must_not_have_edit_authority"):
        validate_verifier_review(attempt, self_review)

    incomplete = json.loads(json.dumps(review))
    incomplete["outputs"].pop()
    with pytest.raises(ValueError, match="verifier_output_coverage_incomplete"):
        validate_verifier_review(attempt, incomplete)


def test_objective_open_items_block_100_but_subjective_options_do_not() -> None:
    valid = {
        "schema_version": "eddy-open-items-v1",
        "objective": [],
        "subjective_optional": [
            {
                "id": "alternate-music-bed",
                "description": "Owner may prefer another equally compliant track.",
            }
        ],
    }
    assert validate_open_items(valid)["objective"] == []

    blocked = json.loads(json.dumps(valid))
    blocked["objective"].append(
        {"id": "clipped-word", "description": "Terminal consonant is missing."}
    )
    with pytest.raises(ValueError, match="objective_open_items_must_be_empty"):
        validate_open_items(blocked)


def test_same_filename_changed_bytes_cannot_reuse_cache_key(tmp_path: Path) -> None:
    source = tmp_path / "decoded.wav"
    source.write_bytes(b"first decode")
    first = content_addressed_cache_key(
        source,
        namespace="delivered-transcript",
        parameters={"model": "medium.en"},
    )
    source.write_bytes(b"rebuilt under the same filename")
    second = content_addressed_cache_key(
        source,
        namespace="delivered-transcript",
        parameters={"model": "medium.en"},
    )
    assert first != second


def test_sample_sequence_and_word_edges_fail_closed() -> None:
    assert sequence_search_parity(
        b"\x01\x02\x03\x04",
        b"\x00\x01\x02\x03\x04",
        max_offset_bytes=1,
    )["pass"]
    assert not sequence_search_parity(
        b"\x01\x02\x03\x04",
        b"\x01\x02\x03",
    )["pass"]
    planned = [
        {"word": "999", "start": 0.0, "end": 0.35},
        {"word": "dollars", "start": 0.36, "end": 0.8},
    ]
    delivered = [
        {"word": "999", "start": 0.06, "end": 0.35},
        {"word": "dollars", "start": 0.36, "end": 0.72},
    ]
    verdict = word_edge_protection_verdict(planned, delivered)
    assert verdict["pass"] is False
    assert len(verdict["issues"]) == 2


def test_shot_latency_protects_declared_pause_but_not_accidental_gap() -> None:
    verdict = shot_entry_latency_verdict(
        [
            {
                "shot_id": "clean-entry",
                "shot_start_seconds": 1.0,
                "speech_onset_seconds": 1.05,
            },
            {
                "shot_id": "deliberate-pause",
                "shot_start_seconds": 2.0,
                "speech_onset_seconds": 2.8,
                "protected_exception": True,
                "exception_id": "pause-1",
            },
        ],
        frame_rate=30,
    )
    assert verdict["pass"] is True
    broken = shot_entry_latency_verdict(
        [
            {
                "shot_id": "late-entry",
                "shot_start_seconds": 1.0,
                "speech_onset_seconds": 1.2,
            }
        ],
        frame_rate=30,
    )
    assert broken["pass"] is False


def test_motion_progressive_captions_and_shared_body_are_measurable() -> None:
    motion = motion_segment_coverage_verdict(
        [
            {
                "segment_id": "mental-model",
                "intended_start_seconds": 0.0,
                "intended_end_seconds": 3.0,
                "first_active_seconds": 0.0,
                "last_active_seconds": 2.8,
                "trailing_frozen_frames": 6,
                "one_frame_flashes": 0,
            }
        ],
        frame_rate=30,
    )
    assert motion["pass"] is False
    captions = progressive_caption_verdict(
        [
            {
                "prior_words": ["This"],
                "active_word": "works",
                "visible_words": ["This", "works"],
                "future_words_visible": False,
                "speaker_id": "speaker-1",
                "speaker_label": "Lennox",
                "speaker_color": "#F97316",
            }
        ],
        multi_speaker=True,
    )
    assert captions["pass"] is True
    digest = "a" * 64
    assert shared_body_hash_verdict(
        {"primary": digest, "alternate-proof": digest, "alternate-stakes": digest}
    )["pass"]


def test_owner_verdict_promotes_generalized_rule_but_rejects_project_fact(
    tmp_path: Path,
) -> None:
    base_issue = {
        "artifact": "long-primary.mp4",
        "evidence": "The repaired shot still enters before speech.",
        "category": "deterministic_bug",
        "scope": "future_edits",
        "desired_correction": "Snap the shot to the measured speech onset.",
        "generalized_rule": (
            "New shots enter within two frames of measured speech unless a protected "
            "exception identifies a deliberate pause."
        ),
        "eval_id": "shot-entry-latency-v1",
        "promotion_class": "owner_profile",
        "source_ref": "owner-verdict:run-1#issue-1",
        "project_fact_fields": [],
    }
    result = record_owner_feedback(
        tmp_path,
        "job-1",
        {
            "schema_version": "owner-verdict-v2",
            "job_id": "job-1",
            "verdict": "changes_requested",
            "approval_scope": ["long-primary"],
            "summary": "Repair the shot entry.",
            "issues": [base_issue],
        },
    )
    assert result["feedback"]["issues"][0]["promotion_class"] == "owner_profile"
    candidates = json.loads(
        (tmp_path / "review" / "correction-candidates.json").read_text()
    )
    assert candidates["candidates"][0]["owner_profile_status"] == "eligible_after_eval"

    literal = {
        **base_issue,
        "generalized_rule": "Always display https://example.test and charge AUD 999.",
        "project_fact_fields": ["url", "offer_or_price"],
    }
    with pytest.raises(ValueError, match="owner_feedback_project_fact_cannot_promote"):
        record_owner_feedback(
            tmp_path,
            "job-1",
            {
                "schema_version": "owner-verdict-v2",
                "job_id": "job-1",
                "verdict": "changes_requested",
                "approval_scope": ["long-primary"],
                "issues": [literal],
            },
        )


def test_v35_independent_review_stops_at_owner_taste_lock(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw-media")
    service = EddyService(
        tmp_path / "runs",
        canonical_root=ROOT,
        auto_prepare=False,
    )
    started = service.edit_start(
        str(source),
        profile_id="lennox-professional-youtube-v2",
    )
    packet = service.host_packet(started["job_id"])
    run = Path(started["run_dir"])
    (run / "assets" / "audio").mkdir(parents=True)
    (run / "assets" / "audio" / "music.wav").write_bytes(b"music")
    (run / "assets" / "audio" / "click.wav").write_bytes(b"click")
    plan = valid_plan_v35()
    plan["source_hashes"] = packet["source_hashes"]
    plan["frame_contract"] = {
        "schema_version": "eddy-project-frame-v3",
        "ref": packet["frame_contract"]["ref"],
        "sha256": packet["frame_contract"]["sha256"],
    }
    plan["contract_bundle"] = {
        "schema_version": "eddy-contract-bundle-ref-v2",
        "ref": packet["contract_bundle"]["ref"],
        "sha256": packet["contract_bundle"]["sha256"],
    }
    plan["project_fact_brief"] = packet["project_fact_brief_ref"]
    submitted = service.host_submit(started["job_id"], plan)
    assert submitted["state"] == "compiling"

    attempt = run / "work" / "attempt-1"
    attempt.mkdir(parents=True)
    outputs = _deliverables(attempt)
    (attempt / "review").mkdir()
    evidence = attempt / "review" / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "eddy-deterministic-evidence-v1",
                "pass": True,
                "measured_by": "fixture-validator",
            }
        )
        + "\n"
    )
    evidence_item = {
        "type": "measurement",
        "ref": "review/evidence.json",
        "sha256": _sha256(evidence),
    }
    rubric = json.loads(
        (run / "contracts" / "quality" / "professional-youtube-100-rubric.json").read_text()
    )
    checks = [
        {
            "id": f"{category['id']}-{index:02d}",
            "points": 1,
            "passed": True,
            "evidence": [evidence_item],
        }
        for category in rubric["categories"]
        for index, _ in enumerate(category["checks"], start=1)
    ]
    review_payload = {
        "schema_version": "eddy-review-submission-v1",
        "review_passes": {
            "schema_version": "eddy-review-passes-v1",
            "passes": [
                {
                    "watch_evidence": evidence_item,
                    "critique": f"objective pass {index}",
                    "repair": "no repair required",
                }
                for index in range(1, 4)
            ],
        },
        "production_score": {
            "schema_version": "eddy-production-score-v1",
            "score": 100,
            "checks": checks,
            "audience_performance": "NOT_RUN",
            "final_authority": "owner_taste_lock",
        },
        "professional_gates": {
            "schema_version": "eddy-professional-gates-v1",
            "gates": {
                gate: {"passed": True, "evidence": [evidence_item]}
                for gate in sorted(REQUIRED_PROFESSIONAL_GATES)
            },
        },
        "verifier_review": {
            "schema_version": "verifier-review-v1",
            "authority": "independent_no_edit_context",
            "edit_authority": False,
            "promotion_recommendation": "objective_green",
            "outputs": [
                {
                    "ref": path.relative_to(attempt).as_posix(),
                    "sha256": _sha256(path),
                    "duration_seconds": 1.0,
                    "watched_seconds": 1.0,
                    "listened_seconds": 1.0,
                    "full_watch": True,
                    "full_listen": True,
                    "defects": [],
                }
                for path in outputs
            ],
        },
        "open_items": {
            "schema_version": "eddy-open-items-v1",
            "objective": [],
            "subjective_optional": [],
        },
    }
    (attempt / "qa.json").write_text(
        json.dumps(
            {
                "gates": {gate: True for gate in sorted(V35_REQUIRED_FINAL_GATES)},
                "blockers": [],
            }
        )
        + "\n"
    )
    service.manager.transition(
        started["job_id"],
        JobState.AWAITING_INDEPENDENT_REVIEW,
    )

    reviewed = service.submit_review(started["job_id"], review_payload)

    assert reviewed["state"] == "proof_gated_candidate_awaiting_owner_taste"
    assert reviewed["proof_state"] == "proof_gated_candidate_awaiting_owner_taste"
    assert reviewed["owner_approved"] is False
    assert (run / "final" / "long-primary.mp4").is_file()


def test_service_start_accepts_project_brief_and_emits_v32_host_packet(
    tmp_path: Path,
) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(
        tmp_path / "runs",
        canonical_root=ROOT,
        auto_prepare=False,
    )

    started = service.edit_start(
        str(source),
        profile_id="lennox-professional-youtube-v2",
        project_brief={
            "schema_version": "eddy-project-fact-brief-v1",
            "project_id": "service-vsl",
            "status": "verified",
            "people": [],
            "facts": [],
            "brand": {"tokens": {}, "asset_refs": []},
            "ui_surfaces": [],
            "output": {"long_captions": False},
            "audio": {"studio_sound_required": True},
            "protected_moments": [],
        },
    )
    packet = service.host_packet(started["job_id"])

    assert packet["schema_version"] == "eddy-host-packet-v3.2"
    assert packet["edit_plan_schema"] == "edit-plan-v3.5"
    assert packet["quality_profile"]["id"] == "lennox-professional-youtube-v2"
    assert packet["project_fact_brief"]["project_id"] == "service-vsl"
    assert packet["verifier_contract"]["authority"] == "independent_no_edit_context"
    bundle = json.loads(
        (Path(started["run_dir"]) / "contracts" / "contract-bundle.json").read_text()
    )
    assert packet["contract_hashes"] == {
        "profile": bundle["profile"]["sha256"],
        "project_fact_brief": bundle["project_fact_brief"]["sha256"],
        "design": bundle["design_contracts"]["design"]["sha256"],
        "long_frame": bundle["design_contracts"]["long_frame"]["sha256"],
        "short_frame": bundle["design_contracts"]["short_frame"]["sha256"],
        "rubric": bundle["quality_evidence"]["rubric"]["sha256"],
        "correction_evals": bundle["quality_evidence"]["correction_evals"]["sha256"],
        "verifier_contract": bundle["quality_evidence"]["verifier_contract"]["sha256"],
        "design_adherence": bundle["quality_evidence"]["design_adherence"]["sha256"],
    }
