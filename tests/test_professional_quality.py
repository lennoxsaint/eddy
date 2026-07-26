from __future__ import annotations

import json
from pathlib import Path

import pytest

from eddy.design_contracts import create_contract_bundle, revise_contract_bundle
from eddy.quality import QualityContractError, resolve_quality_profile
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
    owner.write_text(json.dumps({"profile_id": "lennox-professional-youtube-v1"}))

    owner_profile, _ = resolve_quality_profile(ROOT, owner_state_path=owner)
    explicit_generic, _ = resolve_quality_profile(
        ROOT,
        explicit_profile_id="creator_good_v1",
        owner_state_path=owner,
    )
    owner.unlink()
    generic, _ = resolve_quality_profile(ROOT, owner_state_path=owner)

    assert owner_profile["id"] == "lennox-professional-youtube-v1"
    assert explicit_generic["id"] == "creator_good_v1"
    assert generic["id"] == "creator_good_v1"

    with pytest.raises(QualityContractError, match="quality_profile_unknown"):
        resolve_quality_profile(
            ROOT,
            explicit_profile_id="does-not-exist",
            owner_state_path=owner,
        )


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
    revised = revise_contract_bundle(
        run,
        reason="The proof labels need a larger mobile-safe scale.",
        design_markdown="---\nschema_version: eddy-design-contract-v1\nrevision: 2\n---\n",
    )

    assert revised["design_contracts"]["design"]["revision"] == 2
    assert revised["design_contracts"]["design"]["sha256"] != old_design_hash
    assert revised["invalidation"]["dependent_renders_invalidated"] is True
    bundle = json.loads((run / "contracts" / "contract-bundle.json").read_text())
    assert bundle["revision_history"][0]["reason"].startswith("The proof labels")
