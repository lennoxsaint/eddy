"""Source-safe job state and proof promotion for Eddy."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .editorial import validate_editorial_review
from .plan import EditPlanV3, PlanValidationError
from .professional_proof import (
    REQUIRED_PROFESSIONAL_GATES,
    validate_open_items,
    validate_professional_gate_receipt,
    validate_verifier_review,
)


class JobState(StrEnum):
    QUEUED = "queued"
    PREFLIGHTING = "preflighting"
    AWAITING_HOST_PLAN = "awaiting_host_plan"
    AWAITING_HOST_REPAIR = "awaiting_host_repair"
    AWAITING_OPENING_SELECTION = "awaiting_opening_selection"
    COMPILING = "compiling"
    RENDERING_PROXY = "rendering_proxy"
    ENHANCING_AUDIO = "enhancing_audio"
    RENDERING_FINAL = "rendering_final"
    AWAITING_INDEPENDENT_REVIEW = "awaiting_independent_review"
    VERIFYING = "verifying"
    PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE = (
        "proof_gated_candidate_awaiting_owner_taste"
    )
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


TERMINAL_STATES = {
    JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE,
    JobState.COMPLETED,
    JobState.BLOCKED,
    JobState.CANCELLED,
}
REQUIRED_FINAL_GATES = {
    "three_long_variants",
    "shared_body",
    "shorts_quality",
    "shorts_count",
    "source_lock",
    "editorial_ledger_resolved",
    "shorts_screen_proof",
    "shorts_motion_activity",
    "shorts_caption_sync",
    "caption_terminal_punctuation",
    "quality_profile_bound",
    "design_contracts_bound",
    "hyperframes_doctrine_bound",
    "audio_plan_provenance",
    "music_and_sfx_mix",
    "camera_grade",
    "screen_color_fidelity",
    "minimum_three_complete_review_passes",
    "production_rubric_100",
    "rubric_evidence_complete",
    "audience_performance_not_run",
    "owner_taste_lock",
    "shorts_contextual_motion",
    *(f"hyperframes_motion_hook_{rank}" for rank in range(1, 4)),
    *(f"contextual_motion_hook_{rank}" for rank in range(1, 4)),
    *(f"privacy_masks_hook_{rank}" for rank in range(1, 4)),
    *(f"descript_effect_survival_hook_{rank}" for rank in range(1, 4)),
    *(f"deterministic_qa_hook_{rank}" for rank in range(1, 4)),
}
V35_REQUIRED_FINAL_GATES = REQUIRED_FINAL_GATES | {
    "independent_verifier",
    "objective_open_items_closed",
    "project_fact_brief_bound",
    "verifier_contract_bound",
    "design_adherence_bound",
    *REQUIRED_PROFESSIONAL_GATES,
}


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    source: Path
    snapshot: Path
    run_dir: Path
    state: JobState
    blockers: tuple[str, ...] = ()


class JobManager:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root.expanduser().resolve()
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def start(self, source: Path) -> Job:
        source = source.expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"source_not_found:{source}")
        media = tuple(_source_files(source))
        if not media:
            raise ValueError("source_media_missing")
        job_id = uuid.uuid4().hex
        run_dir = self.runs_root / job_id
        run_dir.mkdir(parents=True)
        hashes = {_source_relative(source, path): _sha256(path) for path in media}
        snapshot = run_dir / "source-snapshot"
        snapshot.mkdir()
        snapshot_hashes: dict[str, str] = {}
        for path in media:
            relative = Path(_source_relative(source, path))
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            snapshot_hashes[relative.as_posix()] = _sha256(destination)
        if snapshot_hashes != hashes:
            raise RuntimeError("source_snapshot_hash_mismatch")
        _write_json(
            run_dir / "source-lock.json",
            {"before": hashes, "snapshot": snapshot_hashes, "after": None},
        )
        job = Job(job_id, source, snapshot, run_dir, JobState.QUEUED)
        self._save(job)
        _receipt(job, "job_started", source=str(source), source_count=len(media))
        return job

    def load(self, job_id: str) -> Job:
        state_path = self.runs_root / job_id / "state.json"
        if not state_path.exists():
            raise KeyError(f"job_not_found:{job_id}")
        payload = json.loads(state_path.read_text())
        return Job(
            id=payload["id"],
            source=Path(payload["source"]),
            snapshot=Path(payload.get("snapshot", payload["source"])),
            run_dir=Path(payload["run_dir"]),
            state=JobState(payload["state"]),
            blockers=tuple(payload.get("blockers", [])),
        )

    def submit_plan(self, job_id: str, payload: dict[str, Any]) -> Job:
        job = self.load(job_id)
        if job.state not in {JobState.AWAITING_HOST_PLAN, JobState.AWAITING_HOST_REPAIR}:
            raise RuntimeError(f"job_not_awaiting_host_plan:{job.state}")
        plan = EditPlanV3.from_dict(payload)
        previous_plan_path = job.run_dir / "edit-plan.json"
        if (
            job.state is JobState.AWAITING_HOST_REPAIR
            and plan.production_review is not None
            and previous_plan_path.is_file()
        ):
            previous = json.loads(previous_plan_path.read_text())
            previous_strategy = (previous.get("production_review") or {}).get("strategy_id")
            if previous_strategy == plan.production_review["strategy_id"]:
                raise PlanValidationError("repair_strategy_must_change")
        lock = json.loads((job.run_dir / "source-lock.json").read_text())
        if plan.source_hashes != lock["before"]:
            raise PlanValidationError("edit_plan_source_hash_mismatch")
        if plan.frame_contract is not None:
            frame_path = (job.run_dir / str(plan.frame_contract["ref"])).resolve()
            _assert_inside(job.run_dir, frame_path)
            if not frame_path.is_file():
                raise PlanValidationError("frame_contract_file_missing")
            if _sha256(frame_path) != plan.frame_contract["sha256"]:
                raise PlanValidationError("frame_contract_hash_mismatch")
        if plan.contract_bundle is not None:
            bundle_path = (job.run_dir / str(plan.contract_bundle["ref"])).resolve()
            _assert_inside(job.run_dir, bundle_path)
            if not bundle_path.is_file():
                raise PlanValidationError("contract_bundle_file_missing")
            if _sha256(bundle_path) != plan.contract_bundle["sha256"]:
                raise PlanValidationError("contract_bundle_hash_mismatch")
            bundle = json.loads(bundle_path.read_text())
            for contract in bundle.get("design_contracts", {}).values():
                contract_path = (job.run_dir / str(contract["ref"])).resolve()
                _assert_inside(job.run_dir, contract_path)
                if not contract_path.is_file() or _sha256(contract_path) != contract["sha256"]:
                    raise PlanValidationError("design_contract_hash_mismatch")
            if plan.schema_version in {"edit-plan-v3.5", "edit-plan-v3.6"}:
                if bundle.get("schema_version") != "eddy-contract-bundle-v2":
                    raise PlanValidationError("contract_bundle_v2_required")
                if (
                    plan.project_fact_brief is None
                    or bundle.get("project_fact_brief", {}).get("sha256")
                    != plan.project_fact_brief.get("sha256")
                ):
                    raise PlanValidationError("project_fact_brief_bundle_mismatch")
        if plan.project_fact_brief is not None:
            brief_path = (job.run_dir / str(plan.project_fact_brief["ref"])).resolve()
            _assert_inside(job.run_dir, brief_path)
            if (
                not brief_path.is_file()
                or _sha256(brief_path) != plan.project_fact_brief["sha256"]
            ):
                raise PlanValidationError("project_fact_brief_hash_mismatch")
            brief = json.loads(brief_path.read_text())
            long_captions = bool(
                ((plan.caption_policy or {}).get("longs") or {}).get("designed_captions")
            )
            if long_captions != bool((brief.get("output") or {}).get("long_captions")):
                raise PlanValidationError("long_caption_project_brief_mismatch")
            fact_ids = {
                str(row.get("id"))
                for row in brief.get("facts", [])
                if isinstance(row, dict)
            }
            for claim in (plan.proof_plan or {}).get("claims", []):
                if not set(claim["factual_bindings"]).issubset(fact_ids):
                    raise PlanValidationError("proof_plan_fact_binding_missing")
        if plan.schema_version == "edit-plan-v3.6":
            opening_contract = plan.opening_visual_contract
            if opening_contract is None:
                raise PlanValidationError("opening_blueprint_contract_required")
            blueprint_path = (
                job.run_dir / str(opening_contract["contract_ref"])
            ).resolve()
            _assert_inside(job.run_dir, blueprint_path)
            if not blueprint_path.is_file():
                raise PlanValidationError("opening_blueprint_contract_file_missing")
            if _sha256(blueprint_path) != opening_contract["contract_sha256"]:
                raise PlanValidationError("opening_blueprint_contract_hash_mismatch")
            source_blueprint = json.loads(blueprint_path.read_text())
            if any(
                opening_contract.get(key) != value
                for key, value in source_blueprint.items()
            ):
                raise PlanValidationError("opening_blueprint_contract_content_mismatch")
            benchmark_binding = opening_contract["benchmark_binding"]
            mechanics_path = (
                job.run_dir / str(benchmark_binding["mechanics_library_ref"])
            ).resolve()
            _assert_inside(job.run_dir, mechanics_path)
            if not mechanics_path.is_file():
                raise PlanValidationError("opening_blueprint_mechanics_library_missing")
            if (
                _sha256(mechanics_path)
                != benchmark_binding["mechanics_library_sha256"]
            ):
                raise PlanValidationError(
                    "opening_blueprint_mechanics_library_hash_mismatch"
                )
            mechanics_library = json.loads(mechanics_path.read_text())
            if (
                not isinstance(mechanics_library, dict)
                or mechanics_library.get("gate_status") != "human_confirmed"
            ):
                raise PlanValidationError(
                    "opening_blueprint_mechanics_library_not_human_confirmed"
                )
            for delivery in (
                plan.opening_blueprint_delivery or {}
            ).get("openings", []):
                for mapping in delivery.get("scene_mappings", []):
                    deviation = mapping.get("deviation")
                    if not isinstance(deviation, dict):
                        continue
                    receipt_path = (
                        job.run_dir / str(deviation["receipt_ref"])
                    ).resolve()
                    _assert_inside(job.run_dir, receipt_path)
                    if not receipt_path.is_file():
                        raise PlanValidationError(
                            "opening_blueprint_deviation_receipt_missing"
                        )
                    if _sha256(receipt_path) != deviation["receipt_sha256"]:
                        raise PlanValidationError(
                            "opening_blueprint_deviation_receipt_hash_mismatch"
                        )
        if plan.audio_plan is not None:
            for cue in [*plan.audio_plan["music"], *plan.audio_plan["sfx"]]:
                cue_path = (job.run_dir / str(cue["ref"])).resolve()
                _assert_inside(job.run_dir, cue_path)
                if not cue_path.is_file():
                    raise PlanValidationError(f"audio_plan_cue_missing:{cue['ref']}")
        if plan.visual_choreography is not None:
            timelines = [
                *plan.visual_choreography["openings"],
                plan.visual_choreography["shared_body"],
                *plan.visual_choreography["shorts"],
            ]
            for timeline in timelines:
                for scene in timeline["scenes"]:
                    for raw_ref in scene["source_refs"]:
                        ref = Path(str(raw_ref))
                        if ref.is_absolute() or ".." in ref.parts:
                            raise PlanValidationError("visual_scene_source_ref_invalid")
                        found = False
                        for root in (job.snapshot.resolve(), job.run_dir.resolve()):
                            candidate = (root / ref).resolve()
                            try:
                                candidate.relative_to(root)
                            except ValueError:
                                continue
                            if candidate.is_file():
                                found = True
                                break
                        if not found:
                            raise PlanValidationError(f"visual_scene_source_ref_missing:{raw_ref}")
        ledger_path = job.run_dir / "editorial-ledger.json"
        if ledger_path.exists():
            blockers = validate_editorial_review(
                json.loads(ledger_path.read_text()),
                plan.to_dict()["editorial_review"],
            )
            if blockers:
                raise PlanValidationError(";".join(blockers))
        _write_json(job.run_dir / "edit-plan.json", plan.to_dict())
        updated = Job(job.id, job.source, job.snapshot, job.run_dir, JobState.COMPILING)
        self._save(updated)
        _receipt(
            updated,
            "host_plan_accepted",
            schema_version=plan.schema_version,
            frame_sha256=(plan.frame_contract or {}).get("sha256"),
            body_structure_source_sha256=(plan.body_structure_contract or {}).get(
                "source_contract_sha256"
            ),
            body_structure_mode=(plan.body_structure_contract or {}).get("mode"),
            body_structure_section_ids=[
                section["section_id"]
                for section in (plan.body_structure_contract or {}).get("sections", [])
            ],
            **_contract_receipt_fields(job),
        )
        return updated

    def transition(self, job_id: str, state: JobState) -> Job:
        job = self.load(job_id)
        if job.state in TERMINAL_STATES:
            raise RuntimeError(f"terminal_job_cannot_transition:{job.state}")
        updated = Job(job.id, job.source, job.snapshot, job.run_dir, state, job.blockers)
        self._save(updated)
        _receipt(updated, "job_state_changed", state=state.value)
        return updated

    def request_owner_repair(self, job_id: str, *, reason: str) -> Job:
        job = self.load(job_id)
        if job.state not in {
            JobState.COMPLETED,
            JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE,
        }:
            raise RuntimeError(f"owner_repair_requires_completed_job:{job.state}")
        if not reason.strip():
            raise ValueError("owner_repair_reason_required")
        final = job.run_dir / "final"
        if not final.is_dir():
            raise RuntimeError("owner_repair_final_missing")
        quarantine = job.run_dir / "quarantine"
        attempt_number = len(list(quarantine.glob("attempt-*"))) + 1
        quarantined = quarantine / f"attempt-{attempt_number}"
        quarantine.mkdir(parents=True, exist_ok=True)
        if quarantined.exists():
            raise RuntimeError(f"quarantine_attempt_exists:{quarantined.name}")
        shutil.move(str(final), str(quarantined))
        blockers = ("owner_directed_repair",)
        _write_json(
            job.run_dir / "repair-packet.json",
            {
                "schema_version": "eddy-repair-packet-v1",
                "attempt": attempt_number,
                "remaining_attempts": None,
                "minimum_complete_passes": 3,
                "repair_policy": "change_strategy_until_green_or_exact_blocker",
                "gates": json.loads((job.run_dir / "verification.json").read_text()).get(
                    "gates", {}
                ) if (job.run_dir / "verification.json").exists() else {},
                "blockers": list(blockers),
                "reason": reason.strip(),
                "quarantine": str(quarantined),
            },
        )
        updated = Job(
            job.id,
            job.source,
            job.snapshot,
            job.run_dir,
            JobState.AWAITING_HOST_REPAIR,
            blockers,
        )
        self._save(updated)
        _receipt(
            updated,
            "owner_repair_requested",
            attempt=attempt_number,
            reason=reason.strip(),
            quarantine=str(quarantined),
            remaining_attempts=None,
        )
        return updated

    def record_owner_approval(self, job_id: str) -> Job:
        """Move an owner-locked candidate to completed after an explicit verdict."""

        job = self.load(job_id)
        if job.state is not JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE:
            raise RuntimeError(f"owner_approval_requires_candidate:{job.state}")
        completed = Job(
            job.id,
            job.source,
            job.snapshot,
            job.run_dir,
            JobState.COMPLETED,
        )
        self._save(completed)
        _receipt(completed, "owner_taste_approved")
        return completed

    def receipt(self, job_id: str, event: str, **details: Any) -> None:
        """Append a public, secret-safe run event from deterministic pipeline stages."""

        _receipt(self.load(job_id), event, **details)

    def claim_finalize(self, job_id: str) -> Job:
        job = self.load(job_id)
        if job.state is not JobState.COMPILING:
            raise RuntimeError(f"job_not_compiled:{job.state}")
        claim = job.run_dir / "finalize.claim"
        try:
            descriptor = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RuntimeError("finalize_already_claimed") from exc
        os.write(descriptor, datetime.now(UTC).isoformat().encode())
        os.close(descriptor)
        _receipt(job, "finalize_claimed")
        return job

    def release_finalize_claim(self, job_id: str) -> None:
        job = self.load(job_id)
        (job.run_dir / "finalize.claim").unlink(missing_ok=True)

    def record_verification(
        self,
        job_id: str,
        *,
        attempt: Path,
        gates: dict[str, bool],
        blockers: list[str],
    ) -> Job:
        job = self.load(job_id)
        attempt = attempt.resolve()
        _assert_inside(job.run_dir, attempt)
        if not attempt.is_dir():
            raise FileNotFoundError(f"attempt_missing:{attempt}")
        source_lock = json.loads((job.run_dir / "source-lock.json").read_text())
        after = {
            _source_relative(job.source, path): _sha256(path)
            for path in _source_files(job.source)
        }
        snapshot_after = {
            path.relative_to(job.snapshot).as_posix(): _sha256(path)
            for path in _source_files(job.snapshot)
        }
        source_lock["after"] = after
        _write_json(job.run_dir / "source-lock.json", source_lock)
        source_green = (
            after == source_lock["before"]
            and snapshot_after == source_lock.get("snapshot")
        )
        verified_gates = {**gates, "source_lock": source_green and gates.get("source_lock", True)}
        plan_path = job.run_dir / "edit-plan.json"
        plan_payload = json.loads(plan_path.read_text()) if plan_path.is_file() else {}
        schema_version = plan_payload.get("schema_version")
        if schema_version in {
            "edit-plan-v3.4",
            "edit-plan-v3.5",
            "edit-plan-v3.6",
        }:
            evidence_gates, evidence_blockers = _production_evidence(job.run_dir, attempt)
            verified_gates.update(evidence_gates)
            binding_gates, binding_blockers = _contract_binding_evidence(
                job.run_dir,
                plan_payload,
            )
            verified_gates.update(binding_gates)
            if schema_version in {"edit-plan-v3.5", "edit-plan-v3.6"}:
                professional_gates, professional_blockers = _professional_v35_evidence(
                    attempt
                )
                verified_gates.update(professional_gates)
                blockers = [*blockers, *professional_blockers]
                verified_gates.update(
                    {
                        "audio_plan_provenance": professional_gates.get(
                            "studio_sound_lineage", False
                        ),
                        "music_and_sfx_mix": professional_gates.get("audio_mix", False)
                        and professional_gates.get("shorts_music_variation", False),
                        "camera_grade": professional_gates.get("camera_grade", False),
                        "screen_color_fidelity": professional_gates.get(
                            "screen_color_fidelity", False
                        ),
                    }
                )
            elif evidence_gates.get("production_rubric_100"):
                verified_gates.update(
                    {
                        "audio_plan_provenance": True,
                        "music_and_sfx_mix": True,
                        "camera_grade": True,
                        "screen_color_fidelity": True,
                    }
                )
            blockers = [*blockers, *evidence_blockers]
            blockers = [*blockers, *binding_blockers]
        else:
            bundle_path = job.run_dir / "contracts" / "contract-bundle.json"
            if bundle_path.is_file():
                profile_id = json.loads(bundle_path.read_text()).get("profile", {}).get("id")
                if profile_id == "lennox-professional-youtube-v2":
                    blockers = [
                        *blockers,
                        "legacy_plan_cannot_claim_lennox_profile_completion",
                    ]
                    for gate in (
                        "quality_profile_bound",
                        "design_contracts_bound",
                        "production_rubric_100",
                        "rubric_evidence_complete",
                    ):
                        verified_gates[gate] = False
        required_gates = (
            V35_REQUIRED_FINAL_GATES
            if schema_version in {"edit-plan-v3.5", "edit-plan-v3.6"}
            else REQUIRED_FINAL_GATES
        )
        missing_gates = sorted(required_gates - set(verified_gates))
        verified_blockers = list(
            dict.fromkeys(
                blockers
                + ([] if source_green else ["source_hash_changed"])
                + [f"required_gate_missing:{gate}" for gate in missing_gates]
            )
        )
        _write_json(
            job.run_dir / "verification.json",
            {"gates": verified_gates, "blockers": verified_blockers},
        )

        if not missing_gates and all(verified_gates.values()) and not verified_blockers:
            contract_bindings = _contract_receipt_fields(job)
            _write_json(
                attempt / "contract-bindings.json",
                {
                    "schema_version": "eddy-output-contract-bindings-v1",
                    **contract_bindings,
                },
            )
            _write_json(attempt / "artifact-manifest.json", {"files": _artifact_hashes(attempt)})
            final = job.run_dir / "final"
            if final.exists():
                raise RuntimeError("final_already_exists")
            shutil.move(str(attempt), str(final))
            final_state = (
                JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE
                if schema_version in {"edit-plan-v3.5", "edit-plan-v3.6"}
                else JobState.COMPLETED
            )
            updated = Job(job.id, job.source, job.snapshot, job.run_dir, final_state)
            _receipt(
                updated,
                "proof_gated_candidate_ready"
                if schema_version in {"edit-plan-v3.5", "edit-plan-v3.6"}
                else "proof_gated_edit_completed",
                **contract_bindings,
            )
        else:
            quarantine = job.run_dir / "quarantine" / attempt.name
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            if quarantine.exists():
                raise RuntimeError(f"quarantine_attempt_exists:{attempt.name}")
            shutil.move(str(attempt), str(quarantine))
            attempt_number = _attempt_number(attempt.name)
            exact_terminal_blocker = any(
                blocker.startswith(("external_blocker:", "technical_blocker:"))
                for blocker in verified_blockers
            )
            _write_json(
                job.run_dir / "repair-packet.json",
                {
                    "schema_version": "eddy-repair-packet-v1",
                    "attempt": attempt_number,
                    "remaining_attempts": None,
                    "minimum_complete_passes": 3,
                    "repair_policy": "change_strategy_until_green_or_exact_blocker",
                    "gates": verified_gates,
                    "blockers": verified_blockers,
                    "quarantine": str(quarantine),
                },
            )
            next_state = JobState.BLOCKED if exact_terminal_blocker else JobState.AWAITING_HOST_REPAIR
            updated = Job(
                job.id,
                job.source,
                job.snapshot,
                job.run_dir,
                next_state,
                tuple(verified_blockers),
            )
            _receipt(
                updated,
                "blocked_attempt_quarantined"
                if exact_terminal_blocker
                else "host_repair_requested",
                blockers=verified_blockers,
                quarantine=str(quarantine),
                remaining_attempts=None,
                repair_policy="change_strategy_until_green_or_exact_blocker",
            )
        self._save(updated)
        return updated

    def cancel(self, job_id: str) -> Job:
        job = self.load(job_id)
        if job.state in TERMINAL_STATES:
            return job
        quarantined = self.quarantine_attempts(job_id)
        cancelled = Job(job.id, job.source, job.snapshot, job.run_dir, JobState.CANCELLED)
        self._save(cancelled)
        _receipt(cancelled, "job_cancelled", quarantine=quarantined)
        return cancelled

    def quarantine_attempts(self, job_id: str) -> list[str]:
        job = self.load(job_id)
        quarantine_root = job.run_dir / "quarantine"
        work_root = job.run_dir / "work"
        quarantined: list[str] = []
        for attempt in sorted(work_root.glob("attempt-*")) if work_root.exists() else ():
            destination = quarantine_root / attempt.name
            quarantine_root.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                continue
            shutil.move(str(attempt), str(destination))
            quarantined.append(str(destination))
        return quarantined

    def block(self, job_id: str, blocker: str) -> Job:
        """Block a job and quarantine every partial candidate attempt."""

        job = self.load(job_id)
        if job.state in TERMINAL_STATES:
            return job
        quarantined = self.quarantine_attempts(job_id)
        blocked = Job(job.id, job.source, job.snapshot, job.run_dir, JobState.BLOCKED, (blocker,))
        self._save(blocked)
        _receipt(blocked, "blocked_attempt_quarantined", blockers=[blocker], quarantine=quarantined)
        return blocked

    def _save(self, job: Job) -> None:
        _write_json(
            job.run_dir / "state.json",
            {
                "id": job.id,
                "source": str(job.source),
                "snapshot": str(job.snapshot),
                "run_dir": str(job.run_dir),
                "state": job.state.value,
                "blockers": list(job.blockers),
            },
        )


def _production_evidence(
    run_dir: Path,
    attempt: Path,
) -> tuple[dict[str, bool], list[str]]:
    """Mechanically recompute shared production gates from bounded evidence files."""

    gates = {
        "minimum_three_complete_review_passes": False,
        "production_rubric_100": False,
        "rubric_evidence_complete": False,
        "audience_performance_not_run": False,
        "owner_taste_lock": False,
    }
    blockers: list[str] = []
    review_path = attempt / "review-passes.json"
    score_path = attempt / "production-score.json"
    if not review_path.is_file():
        blockers.append("production_review_passes_missing")
    else:
        try:
            review = json.loads(review_path.read_text())
            passes = review.get("passes", [])
            complete = (
                review.get("schema_version") == "eddy-review-passes-v1"
                and isinstance(passes, list)
                and len(passes) >= 3
                and all(
                    isinstance(row, dict)
                    and all(row.get(key) for key in ("watch_evidence", "critique", "repair"))
                    for row in passes
                )
            )
            gates["minimum_three_complete_review_passes"] = complete
            if not complete:
                blockers.append("production_review_passes_incomplete")
        except (json.JSONDecodeError, OSError):
            blockers.append("production_review_passes_invalid")
    if not score_path.is_file():
        blockers.append("production_score_missing")
        return gates, blockers
    try:
        score = json.loads(score_path.read_text())
    except (json.JSONDecodeError, OSError):
        blockers.append("production_score_invalid")
        return gates, blockers
    checks = score.get("checks")
    allowed_evidence = {"file", "frame", "timestamp", "hash", "playback", "measurement"}
    expected_ids: set[str] = set()
    bundle_path = run_dir / "contracts" / "contract-bundle.json"
    if bundle_path.is_file():
        bundle = json.loads(bundle_path.read_text())
        rubric_ref = (bundle.get("quality_evidence", {}).get("rubric") or {}).get("ref")
        if isinstance(rubric_ref, str):
            rubric_path = run_dir / rubric_ref
            if rubric_path.is_file():
                rubric = json.loads(rubric_path.read_text())
                expected_ids = {
                    f"{category['id']}-{index:02d}"
                    for category in rubric.get("categories", [])
                    for index, _ in enumerate(category.get("checks", []), start=1)
                }
    evidence_complete = (
        score.get("schema_version") == "eddy-production-score-v1"
        and isinstance(checks, list)
        and len(checks) == 100
        and {row.get("id") for row in checks if isinstance(row, dict)} == expected_ids
        and all(
            isinstance(row, dict)
            and row.get("passed") is True
            and row.get("points") == 1
            and isinstance(row.get("evidence"), list)
            and bool(row["evidence"])
            and all(
                isinstance(item, dict)
                and item.get("type") in allowed_evidence
                and isinstance(item.get("ref"), str)
                and bool(item["ref"].strip())
                and _evidence_ref_exists(run_dir, attempt, item["ref"])
                for item in row["evidence"]
            )
            for row in checks
        )
    )
    calculated_score = (
        sum(int(row["points"]) for row in checks)
        if evidence_complete and isinstance(checks, list)
        else 0
    )
    gates["rubric_evidence_complete"] = evidence_complete
    gates["production_rubric_100"] = calculated_score == 100 and score.get("score") == 100
    gates["audience_performance_not_run"] = score.get("audience_performance") == "NOT_RUN"
    gates["owner_taste_lock"] = score.get("final_authority") == "owner_taste_lock"
    if not evidence_complete:
        blockers.append("rubric_evidence_incomplete")
    if not gates["production_rubric_100"]:
        blockers.append(f"production_score_not_100:{calculated_score}")
    if not gates["audience_performance_not_run"]:
        blockers.append("audience_performance_state_invalid")
    if not gates["owner_taste_lock"]:
        blockers.append("owner_taste_lock_missing")
    return gates, blockers


def _professional_v35_evidence(
    attempt: Path,
) -> tuple[dict[str, bool], list[str]]:
    """Recompute v3.5 gates from independent, hash-bound review artifacts."""

    gates = {
        **{gate: False for gate in REQUIRED_PROFESSIONAL_GATES},
        "independent_verifier": False,
        "objective_open_items_closed": False,
    }
    blockers: list[str] = []
    paths = {
        "professional_gates": attempt / "professional-gates.json",
        "verifier_review": attempt / "verifier-review.json",
        "open_items": attempt / "open-items.json",
    }
    payloads: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        if not path.is_file():
            blockers.append(f"{label}_missing")
            continue
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            blockers.append(f"{label}_invalid")
            continue
        if not isinstance(payload, dict):
            blockers.append(f"{label}_invalid")
            continue
        payloads[label] = payload
    professional = payloads.get("professional_gates")
    if professional is not None:
        try:
            gates.update(validate_professional_gate_receipt(attempt, professional))
        except ValueError as exc:
            blockers.append(str(exc))
    verifier = payloads.get("verifier_review")
    if verifier is not None:
        try:
            validate_verifier_review(attempt, verifier)
            gates["independent_verifier"] = True
        except ValueError as exc:
            blockers.append(str(exc))
    open_items = payloads.get("open_items")
    if open_items is not None:
        try:
            validate_open_items(open_items)
            gates["objective_open_items_closed"] = True
        except ValueError as exc:
            blockers.append(str(exc))

    review_path = attempt / "review-passes.json"
    if review_path.is_file():
        try:
            review = json.loads(review_path.read_text())
        except (json.JSONDecodeError, OSError):
            review = {}
        for index, row in enumerate(review.get("passes", []), start=1):
            evidence = row.get("watch_evidence") if isinstance(row, dict) else None
            if not isinstance(evidence, dict):
                blockers.append(f"review_pass_evidence_not_hash_bound:{index}")
                gates["independent_verifier"] = False
                continue
            try:
                _validate_review_evidence(attempt, evidence)
            except ValueError as exc:
                blockers.append(f"{exc}:{index}")
                gates["independent_verifier"] = False
    score_path = attempt / "production-score.json"
    if score_path.is_file():
        try:
            score = json.loads(score_path.read_text())
        except (json.JSONDecodeError, OSError):
            score = {}
        for row in score.get("checks", []):
            if not isinstance(row, dict):
                continue
            for evidence in row.get("evidence", []):
                if not isinstance(evidence, dict):
                    blockers.append("rubric_evidence_not_hash_bound")
                    gates["rubric_evidence_complete"] = False
                    continue
                try:
                    _validate_review_evidence(attempt, evidence)
                except ValueError as exc:
                    blockers.append(str(exc))
                    gates["rubric_evidence_complete"] = False
    return gates, list(dict.fromkeys(blockers))


def _contract_receipt_fields(job: Job) -> dict[str, Any]:
    bundle_path = job.run_dir / "contracts" / "contract-bundle.json"
    if not bundle_path.is_file():
        return {}
    bundle = json.loads(bundle_path.read_text())
    design = bundle.get("design_contracts", {})
    profile = bundle.get("profile", {})
    quality = bundle.get("quality_evidence", {})
    return {
        "contract_bundle_sha256": _sha256(bundle_path),
        "quality_profile_id": profile.get("id"),
        "quality_profile_sha256": profile.get("sha256"),
        "project_fact_brief_sha256": (
            bundle.get("project_fact_brief") or {}
        ).get("sha256"),
        "design_sha256": (design.get("design") or {}).get("sha256"),
        "long_frame_sha256": (design.get("long_frame") or {}).get("sha256"),
        "short_frame_sha256": (design.get("short_frame") or {}).get("sha256"),
        "rubric_sha256": (quality.get("rubric") or {}).get("sha256"),
        "correction_evals_sha256": (
            quality.get("correction_evals") or {}
        ).get("sha256"),
        "verifier_contract_sha256": (
            quality.get("verifier_contract") or {}
        ).get("sha256"),
        "design_adherence_sha256": (
            quality.get("design_adherence") or {}
        ).get("sha256"),
    }


def _contract_binding_evidence(
    run_dir: Path,
    plan_payload: dict[str, Any],
) -> tuple[dict[str, bool], list[str]]:
    gates = {
        "quality_profile_bound": False,
        "design_contracts_bound": False,
        "hyperframes_doctrine_bound": False,
    }
    blockers: list[str] = []
    ref = plan_payload.get("contract_bundle") or {}
    bundle_path = run_dir / str(ref.get("ref", "missing"))
    if not bundle_path.is_file() or _sha256(bundle_path) != ref.get("sha256"):
        return gates, ["contract_bundle_binding_invalid"]
    bundle = json.loads(bundle_path.read_text())
    profile = bundle.get("profile", {})
    profile_path = run_dir / str(profile.get("ref", "missing"))
    try:
        profile_payload = json.loads(profile_path.read_text())
    except (json.JSONDecodeError, OSError):
        profile_payload = {}
    gates["quality_profile_bound"] = (
        isinstance(profile.get("id"), str)
        and bool(profile["id"])
        and profile_payload.get("id") == profile["id"]
        and profile_payload.get("schema_version")
        in {
            "eddy-quality-profile-v1",
            "eddy-quality-profile-v2",
            "eddy-quality-profile-v3",
        }
        and _sha256(profile_path) == profile.get("sha256")
    )
    design_rows = bundle.get("design_contracts", {})
    gates["design_contracts_bound"] = (
        isinstance(design_rows, dict)
        and set(design_rows) == {"design", "long_frame", "short_frame"}
        and all(isinstance(row, dict) for row in design_rows.values())
        and all(
        (run_dir / str(row.get("ref", "missing"))).is_file()
        and _sha256(run_dir / str(row["ref"])) == row.get("sha256")
        for row in design_rows.values()
        )
    )
    hyperframes = bundle.get("hyperframes", {})
    hyperframe_references = hyperframes.get("references", {})
    gates["hyperframes_doctrine_bound"] = (
        hyperframes.get("version") == "0.7.3"
        and hyperframes.get("commit")
        == "997823b6b523eb4d43e0f03c140f5897f13ce780"
        and isinstance(hyperframe_references, dict)
        and len(hyperframe_references) == 4
        and all(
            isinstance(row, dict)
            for row in hyperframe_references.values()
        )
        and all(
            (run_dir / str(row.get("ref", "missing"))).is_file()
            and _sha256(run_dir / str(row["ref"])) == row.get("sha256")
            for row in hyperframe_references.values()
            if isinstance(row, dict)
        )
    )
    if bundle.get("schema_version") == "eddy-contract-bundle-v2":
        fact = bundle.get("project_fact_brief", {})
        fact_path = run_dir / str(fact.get("ref", "missing"))
        gates["project_fact_brief_bound"] = (
            fact.get("schema_version") == "eddy-project-fact-brief-ref-v1"
            and fact_path.is_file()
            and _sha256(fact_path) == fact.get("sha256")
        )
        verifier = (bundle.get("quality_evidence") or {}).get(
            "verifier_contract",
            {},
        )
        verifier_path = run_dir / str(verifier.get("ref", "missing"))
        gates["verifier_contract_bound"] = (
            verifier_path.is_file()
            and _sha256(verifier_path) == verifier.get("sha256")
        )
        adherence = (bundle.get("quality_evidence") or {}).get(
            "design_adherence",
            {},
        )
        adherence_path = run_dir / str(adherence.get("ref", "missing"))
        try:
            adherence_payload = json.loads(adherence_path.read_text())
        except (json.JSONDecodeError, OSError):
            adherence_payload = {}
        gates["design_adherence_bound"] = (
            adherence_path.is_file()
            and _sha256(adherence_path) == adherence.get("sha256")
            and adherence_payload.get("schema_version") == "eddy-design-adherence-v1"
            and adherence_payload.get("pass") is True
            and all(
                (adherence_payload.get("files") or {}).get(label, {}).get("sha256")
                == row.get("sha256")
                for label, row in design_rows.items()
            )
        )
    for gate, passed in gates.items():
        if not passed:
            blockers.append(f"{gate}_invalid")
    return gates, blockers


def _validate_review_evidence(attempt: Path, value: dict[str, Any]) -> None:
    ref = value.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("review_pass_evidence_ref_invalid")
    path_ref = Path(ref.split("#", 1)[0])
    if path_ref.is_absolute() or ".." in path_ref.parts:
        raise ValueError("review_pass_evidence_ref_invalid")
    path = attempt / path_ref
    if not path.is_file():
        raise ValueError("review_pass_evidence_missing")
    if value.get("sha256") != _sha256(path):
        raise ValueError("review_pass_evidence_hash_mismatch")


def _evidence_ref_exists(run_dir: Path, attempt: Path, raw_ref: str) -> bool:
    base = raw_ref.split("#", 1)[0]
    ref = Path(base)
    if not base or ref.is_absolute() or ".." in ref.parts:
        return False
    return any((root / ref).is_file() for root in (attempt, run_dir))


def _source_files(source: Path) -> list[Path]:
    allowed = {".mp4", ".mov", ".mkv", ".webm", ".wav", ".m4a", ".mp3"}
    if source.is_file():
        return [source] if source.suffix.lower() in allowed else []
    top_level = sorted(
        path
        for path in source.iterdir()
        if path.is_file() and path.suffix.lower() in allowed
    )
    if top_level:
        return top_level
    ignored_directories = {
        "runs",
        "eddy-runs",
        "final",
        "work",
        "output",
        "outputs",
        "cache",
        "quarantine",
        "post-production",
    }
    return sorted(
        path
        for path in source.rglob("*")
        if path.is_file()
        and path.suffix.lower() in allowed
        and not ignored_directories.intersection(part.lower() for part in path.relative_to(source).parts)
    )


def _source_relative(source: Path, path: Path) -> str:
    return path.name if source.is_file() else path.relative_to(source).as_posix()


def _artifact_hashes(attempt: Path) -> dict[str, str]:
    return {
        path.relative_to(attempt).as_posix(): _sha256(path)
        for path in sorted(attempt.rglob("*"))
        if path.is_file() and path.name != "artifact-manifest.json"
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _receipt(job: Job, event: str, **details: Any) -> None:
    payload = {
        "at": datetime.now(UTC).isoformat(),
        "event": event,
        "job_id": job.id,
        "state": job.state.value,
        **details,
    }
    with (job.run_dir / "receipts.jsonl").open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _assert_inside(parent: Path, child: Path) -> None:
    try:
        child.relative_to(parent.resolve())
    except ValueError as exc:
        raise ValueError(f"path_outside_run:{child}") from exc


def _attempt_number(name: str) -> int:
    try:
        number = int(name.removeprefix("attempt-"))
    except ValueError:
        return 3
    return max(1, number)
