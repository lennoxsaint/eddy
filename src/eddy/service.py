"""Public service boundary shared by CLI and MCP adapters."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .choreography import rank_opening_candidates
from .contract import canonical_contract
from .caption_repair import repair_captions
from .design_contracts import create_contract_bundle, revise_contract_bundle
from .feedback import record_owner_feedback
from .owner_plugin import owner_plugin_status
from .privacy_repair import repair_short_privacy
from .opening_blueprint import validate_opening_blueprint_contract
from .project_brief import materialize_project_fact_brief
from .quality import resolve_quality_profile
from .review_submission import write_review_submission
from .runtime import JobManager, JobState
from .sync import CANONICAL_SURFACES, canonical_surface_commit, check_projection
from .support import create_support_bundle
from .trust import trust_status


OPENING_BLUEPRINT_RELATIVE = Path(
    "pre-production/review/opening-edit-blueprint.json"
)


def _find_opening_blueprint(source: Path) -> Path | None:
    current = source if source.is_dir() else source.parent
    for root in (current, *current.parents):
        candidate = root / OPENING_BLUEPRINT_RELATIVE
        if candidate.is_file():
            return candidate
    return None


def _snapshot_opening_blueprint(source: Path, run_dir: Path) -> dict[str, Any] | None:
    blueprint_source = _find_opening_blueprint(source)
    if blueprint_source is None:
        return None
    blueprint = json.loads(blueprint_source.read_text())
    if not isinstance(blueprint, dict):
        raise ValueError("opening_edit_blueprint_must_be_object")
    project_root = blueprint_source.parents[2]
    binding = blueprint.get("benchmark_binding")
    if not isinstance(binding, dict):
        raise ValueError("opening_blueprint_benchmark_binding_required")
    mechanics_ref = binding.get("mechanics_library_ref")
    if not isinstance(mechanics_ref, str) or not mechanics_ref.strip():
        raise ValueError("opening_blueprint_mechanics_library_ref_required")
    mechanics_relative = Path(mechanics_ref)
    if mechanics_relative.is_absolute() or ".." in mechanics_relative.parts:
        raise ValueError("opening_blueprint_mechanics_library_ref_invalid")
    mechanics_source = (project_root / mechanics_relative).resolve()
    try:
        mechanics_source.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ValueError("opening_blueprint_mechanics_library_ref_invalid") from exc
    if not mechanics_source.is_file():
        raise ValueError("opening_blueprint_mechanics_library_missing")
    expected_mechanics_hash = binding.get("mechanics_library_sha256")
    if hashlib.sha256(mechanics_source.read_bytes()).hexdigest() != expected_mechanics_hash:
        raise ValueError("opening_blueprint_mechanics_library_hash_mismatch")
    mechanics_library = json.loads(mechanics_source.read_text())
    if (
        not isinstance(mechanics_library, dict)
        or mechanics_library.get("gate_status") != "human_confirmed"
    ):
        raise ValueError("opening_blueprint_mechanics_library_not_human_confirmed")

    blueprint_target = run_dir / OPENING_BLUEPRINT_RELATIVE
    blueprint_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(blueprint_source, blueprint_target)
    mechanics_target = run_dir / mechanics_relative
    mechanics_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mechanics_source, mechanics_target)
    snapshotted = {
        **blueprint,
        "contract_ref": OPENING_BLUEPRINT_RELATIVE.as_posix(),
        "contract_sha256": hashlib.sha256(blueprint_target.read_bytes()).hexdigest(),
    }
    variants = snapshotted.get("variants")
    hook_ids = (
        [str(row.get("hook_id")) for row in variants if isinstance(row, dict)]
        if isinstance(variants, list)
        else []
    )
    validate_opening_blueprint_contract(snapshotted, hook_ids=hook_ids)
    return snapshotted


def _worker_inspection_command(pid: int, platform_name: str) -> list[str]:
    if platform_name == "nt":
        return [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "(Get-CimInstance Win32_Process "
                f'-Filter "ProcessId = {pid}").CommandLine'
            ),
        ]
    return ["ps", "-p", str(pid), "-o", "command="]


def _worker_command_line(pid: int) -> str:
    return subprocess.run(
        _worker_inspection_command(pid, os.name),
        capture_output=True,
        text=True,
        check=False,
    ).stdout


def _terminate_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return
    kill_process_group = getattr(os, "killpg", None)
    if not callable(kill_process_group):
        raise OSError("process_group_termination_unavailable")
    kill_process_group(pid, signal.SIGTERM)


class EddyService:
    def __init__(
        self,
        runs_root: Path,
        *,
        canonical_root: Path | None = None,
        auto_prepare: bool = True,
    ) -> None:
        self.manager = JobManager(runs_root)
        self.canonical_root = (
            canonical_root.resolve()
            if canonical_root
            else Path(__file__).resolve().parents[2]
        )
        self.auto_prepare = auto_prepare

    def edit_options(
        self,
        source: str,
        *,
        format: str = "youtube",
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        path = Path(source).expanduser().resolve()
        if format != "youtube":
            raise ValueError(f"unsupported_format:{format}")
        if not path.exists():
            raise FileNotFoundError(f"source_not_found:{path}")
        profile, _ = resolve_quality_profile(
            self.canonical_root,
            explicit_profile_id=profile_id,
        )
        option = {
            "id": "skill_first",
            "name": "Eddy",
            "benefits": "Host-model editorial taste with deterministic local mechanics and proof gates.",
            "drawbacks": "Final audio blocks if real Descript effects do not survive export.",
            "privacy": "local_media_with_private_descript_audio_egress",
            "cost": "Descript usage may consume account credits; no other metered fallback is allowed.",
        }
        return {
            "requires_choice": False,
            "selected_option_id": "skill_first",
            "options": [option],
            "quality_profile_id": profile["id"],
        }

    def edit_start(
        self,
        source: str,
        *,
        format: str = "youtube",
        profile_id: str | None = None,
        project_brief: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.edit_options(source, format=format, profile_id=profile_id)
        profile, profile_path = resolve_quality_profile(
            self.canonical_root,
            explicit_profile_id=profile_id,
        )
        job = self.manager.start(Path(source))
        source_lock = json.loads((job.run_dir / "source-lock.json").read_text())
        project_fact_brief = materialize_project_fact_brief(
            job.run_dir,
            source=job.source,
            explicit=project_brief,
        )
        create_contract_bundle(
            job.run_dir,
            source=job.source,
            canonical_root=self.canonical_root,
            profile=profile,
            profile_path=profile_path,
            source_hashes=source_lock["before"],
            project_fact_brief=project_fact_brief,
        )
        opening_blueprint = _snapshot_opening_blueprint(job.source, job.run_dir)
        created_bundle = json.loads(
            (job.run_dir / "contracts" / "contract-bundle.json").read_text()
        )
        self.manager.receipt(
            job.id,
            "quality_contract_bundle_created",
            profile_id=profile["id"],
            contract_bundle_sha256=hashlib.sha256(
                (job.run_dir / "contracts" / "contract-bundle.json").read_bytes()
            ).hexdigest(),
            quality_profile_sha256=created_bundle["profile"]["sha256"],
            design_sha256=created_bundle["design_contracts"]["design"]["sha256"],
            long_frame_sha256=created_bundle["design_contracts"]["long_frame"]["sha256"],
            short_frame_sha256=created_bundle["design_contracts"]["short_frame"]["sha256"],
            project_fact_brief_sha256=created_bundle["project_fact_brief"]["sha256"],
            opening_blueprint_sha256=(
                opening_blueprint["contract_sha256"]
                if opening_blueprint is not None
                else None
            ),
        )
        if self.auto_prepare:
            self._launch_worker("prepare", job.id)
        else:
            job = self.manager.transition(job.id, JobState.AWAITING_HOST_PLAN)
        return self._job_payload(job)

    def job_status(self, job_id: str) -> dict[str, Any]:
        return self._job_payload(self.manager.load(job_id))

    def host_packet(self, job_id: str) -> dict[str, Any]:
        job = self.manager.load(job_id)
        source_lock = json.loads((job.run_dir / "source-lock.json").read_text())
        transcript_path = job.run_dir / "transcript.json"
        ledger_path = job.run_dir / "editorial-ledger.json"
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {
            "chunks": [],
            "candidates": [],
        }
        proof_assets = [
            {
                "path": path.relative_to(job.snapshot).as_posix(),
                "kind": "image",
            }
            for path in sorted(job.snapshot.rglob("*"))
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        screen_sources = [
            relative
            for relative in source_lock["before"]
            if "screen" in relative.lower() or "display" in relative.lower()
        ]
        opening_blueprint_path = job.run_dir / OPENING_BLUEPRINT_RELATIVE
        opening_blueprint = None
        if opening_blueprint_path.is_file():
            raw_blueprint = json.loads(opening_blueprint_path.read_text())
            opening_blueprint = {
                **raw_blueprint,
                "contract_ref": OPENING_BLUEPRINT_RELATIVE.as_posix(),
                "contract_sha256": hashlib.sha256(
                    opening_blueprint_path.read_bytes()
                ).hexdigest(),
            }
        current_edit_plan_schema = (
            "edit-plan-v3.6" if opening_blueprint is not None else "edit-plan-v3.5"
        )
        bundle_path = job.run_dir / "contracts" / "contract-bundle.json"
        if not bundle_path.is_file():
            raise RuntimeError("contract_bundle_missing")
        bundle = json.loads(bundle_path.read_text())
        quality_profile_path = job.run_dir / str(bundle["profile"]["ref"])
        project_fact_path = job.run_dir / str(bundle["project_fact_brief"]["ref"])
        frame_path = job.run_dir / "frame.md"
        short_frame_path = job.run_dir / "shorts" / "frame.md"
        design_path = job.run_dir / "design.md"
        frame_sha256 = hashlib.sha256(frame_path.read_bytes()).hexdigest()
        short_frame_sha256 = hashlib.sha256(short_frame_path.read_bytes()).hexdigest()
        design_sha256 = hashlib.sha256(design_path.read_bytes()).hexdigest()
        bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        return {
            "schema_version": "eddy-host-packet-v3.2",
            "job_id": job.id,
            "state": job.state.value,
            "source_hashes": source_lock["before"],
            "transcript": json.loads(transcript_path.read_text()) if transcript_path.exists() else None,
            "transcript_chunks": ledger.get("chunks", []),
            "editorial_ledger": ledger,
            "long_gaps": [
                item for item in ledger.get("candidates", []) if item.get("kind") == "long_gap"
            ],
            "proof_assets": proof_assets,
            "screen_sources": screen_sources,
            "screen_proof_candidates": [
                {
                    "id": chunk["id"],
                    "start": chunk["start"],
                    "end": chunk["end"],
                    "text": chunk["text"],
                }
                for chunk in ledger.get("chunks", [])
            ],
            "motion_requirements": {
                "longs": {
                    "minimum_animated_beats_per_hook": 2,
                    "render_host_authored_plan": True,
                    "opening_proof_trailer": {
                        "variants": 3,
                        "meaningful_visual_beats_first_30_min": 8,
                        "frame_one_activity_by_second": 0.04,
                        "money_shot_by_second": 3,
                        "real_proof_by_second": 10,
                        "stakes_by_second": 30,
                        "max_unexplained_static_hold_seconds": 4,
                        "requires_muted_mobile_and_taste_passes": True,
                    },
                    "opening_edit_blueprint": {
                        "contract_version": "2.0",
                        "delivery_schema": "eddy-opening-blueprint-delivery-v1",
                        "function_policy": "function_locked_style_flexible",
                        "opening_window_seconds": [0, 30],
                        "bridge_window_seconds": [30, 60],
                        "every_delivered_scene_requires_mapping": True,
                        "deviation_receipt_required": True,
                    },
                    "adaptive_cadence": {
                        "target_seconds": [6, 12],
                        "reason_required_after_seconds": 8,
                        "hard_max_seconds": 12,
                        "max_same_layout_repeats": 2,
                    },
                },
                "shorts": {
                    "minimum_screen_share": 0.25,
                    "minimum_animated_beats": 2,
                    "hook_beat_starts_by_s": 2.0,
                    "adaptive_cadence_seconds": [4, 8],
                    "brand_act_wipe_max": 1,
                },
                "visual_choreography": {
                    "schema_version": "eddy-visual-choreography-v1",
                    "opening_timelines": 3,
                    "shared_body_timelines": 1,
                    "portrait_timeline_per_short": True,
                    "layouts": [
                        "proof_canvas",
                        "speaker_full",
                        "speaker_close",
                        "speaker_tight",
                        "speaker_edge_left",
                        "speaker_edge_right",
                        "speaker_pip",
                        "pip_bottom_right",
                        "pip_bottom_left",
                        "pip_top_right",
                        "pip_top_left",
                        "vertical_speaker_left",
                        "vertical_speaker_right",
                        "embedded_split_left",
                        "embedded_split_right",
                        "speaker_plus_mental_model",
                        "speaker_top_screen_bottom",
                        "source_screen",
                        "illustration_canvas",
                        "special_emphasis",
                    ],
                    "evidence_authority": [
                        "raw_source",
                        "supplied_asset",
                        "pixel_faithful_capture",
                        "fact_bound_reconstruction",
                        "diagram",
                        "metaphor",
                    ],
                    "transitions": [
                        "hard_cut",
                        "continuation_crossfade",
                        "semantic_push",
                        "scale_match",
                        "brand_act_wipe",
                    ],
                },
            },
            "prior_repair": (
                json.loads((job.run_dir / "repair-packet.json").read_text())
                if (job.run_dir / "repair-packet.json").exists()
                else None
            ),
            "requested_host_action": (
                "repair_edit_plan_from_prior_evidence"
                if (job.run_dir / "repair-packet.json").exists()
                else "review_every_chunk_and_resolve_every_ledger_item"
            ),
            "edit_plan_schema": current_edit_plan_schema,
            "accepted_edit_plan_schemas": [
                "edit-plan-v3",
                "edit-plan-v3.1",
                "edit-plan-v3.2",
                "edit-plan-v3.3",
                "edit-plan-v3.4",
                "edit-plan-v3.5",
                "edit-plan-v3.6",
            ],
            "frame_contract": {
                "schema_version": "eddy-project-frame-v3",
                "path": str(frame_path),
                "ref": "frame.md",
                "sha256": frame_sha256,
            },
            "design_contracts": {
                "design": {
                    "schema_version": "eddy-design-contract-v2",
                    "path": str(design_path),
                    "ref": "design.md",
                    "sha256": design_sha256,
                    "revision": bundle["design_contracts"]["design"]["revision"],
                },
                "long_frame": {
                    "schema_version": "eddy-project-frame-v3",
                    "path": str(frame_path),
                    "ref": "frame.md",
                    "sha256": frame_sha256,
                    "revision": bundle["design_contracts"]["long_frame"]["revision"],
                },
                "short_frame": {
                    "schema_version": "eddy-project-frame-v3",
                    "path": str(short_frame_path),
                    "ref": "shorts/frame.md",
                    "sha256": short_frame_sha256,
                    "revision": bundle["design_contracts"]["short_frame"]["revision"],
                },
            },
            "contract_bundle": {
                "schema_version": "eddy-contract-bundle-ref-v2",
                "path": str(bundle_path),
                "ref": "contracts/contract-bundle.json",
                "sha256": bundle_sha256,
            },
            "contract_hashes": {
                "profile": bundle["profile"]["sha256"],
                "project_fact_brief": bundle["project_fact_brief"]["sha256"],
                "design": bundle["design_contracts"]["design"]["sha256"],
                "long_frame": bundle["design_contracts"]["long_frame"]["sha256"],
                "short_frame": bundle["design_contracts"]["short_frame"]["sha256"],
                "rubric": bundle["quality_evidence"]["rubric"]["sha256"],
                "correction_evals": bundle["quality_evidence"]["correction_evals"][
                    "sha256"
                ],
                "verifier_contract": bundle["quality_evidence"]["verifier_contract"][
                    "sha256"
                ],
                "design_adherence": bundle["quality_evidence"]["design_adherence"][
                    "sha256"
                ],
            },
            "quality_profile": json.loads(quality_profile_path.read_text()),
            "project_fact_brief": json.loads(project_fact_path.read_text()),
            "opening_edit_blueprint": opening_blueprint,
            "project_fact_brief_ref": bundle["project_fact_brief"],
            "verifier_contract": json.loads(
                (
                    job.run_dir
                    / str(bundle["quality_evidence"]["verifier_contract"]["ref"])
                ).read_text()
            ),
            "audio_policy": bundle["audio_policy"],
            "caption_policy": json.loads(quality_profile_path.read_text())["captions"],
            "grade_policy": json.loads(quality_profile_path.read_text()).get("grade", {}),
            "completion_policy": json.loads(quality_profile_path.read_text()).get("review", {}),
            "requirements": {
                "primary_hooks": 1,
                "alternate_hooks": 2,
                "shared_body": True,
                "packaging": False,
                "opening_blueprint_delivery": {
                    "required": opening_blueprint is not None,
                    "schema_version": "eddy-opening-blueprint-delivery-v1",
                    "map_through_second": 60,
                    "deviation_receipts_required": True,
                },
                "body_structure_contract": {
                    "schema_version": "eddy-body-structure-v1",
                    "modes": ["countable_guide", "live_test", "proof_led_argument"],
                    "section_count": [3, 5],
                    "route_understood_by_second": 30,
                    "progress_cue_per_non_final_boundary": True,
                    "major_order_authority": "sage_locked_eddy_may_not_reorder",
                    "source_ref": "pre-production/review/script-structure-contract.json#body_structure",
                },
            },
        }

    def host_submit(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        job = self.manager.submit_plan(job_id, payload)
        result = self._job_payload(job)
        if payload.get("schema_version") in {
            "edit-plan-v3.2",
            "edit-plan-v3.3",
            "edit-plan-v3.4",
            "edit-plan-v3.5",
            "edit-plan-v3.6",
        }:
            opening_selection = self.opening_candidates(job_id)
            result = {**self._job_payload(self.manager.load(job_id)), "opening_selection": opening_selection}
        return result

    def revise_design_contracts(
        self,
        job_id: str,
        *,
        reason: str,
        design_markdown: str | None = None,
        long_frame_markdown: str | None = None,
        short_frame_markdown: str | None = None,
    ) -> dict[str, Any]:
        job = self.manager.load(job_id)
        if job.state not in {
            JobState.AWAITING_HOST_PLAN,
            JobState.AWAITING_HOST_REPAIR,
            JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE,
            JobState.COMPLETED,
        }:
            raise RuntimeError(f"design_contract_revision_unavailable:{job.state}")
        if job.state in {
            JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE,
            JobState.COMPLETED,
        }:
            job = self.manager.request_owner_repair(
                job_id,
                reason=f"systemic_design_contract_repair:{reason}",
            )
        result = revise_contract_bundle(
            job.run_dir,
            reason=reason,
            design_markdown=design_markdown,
            long_frame_markdown=long_frame_markdown,
            short_frame_markdown=short_frame_markdown,
        )
        (job.run_dir / "edit-plan.json").unlink(missing_ok=True)
        self.manager.receipt(
            job.id,
            "design_contract_revised",
            reason=reason.strip(),
            contract_bundle_sha256=result["sha256"],
            dependent_renders_invalidated=True,
        )
        return {**result, "job": self._job_payload(self.manager.load(job.id))}

    def opening_candidates(self, job_id: str) -> dict[str, Any]:
        job = self.manager.load(job_id)
        if job.state not in {JobState.COMPILING, JobState.AWAITING_OPENING_SELECTION}:
            raise RuntimeError(f"opening_candidates_unavailable:{job.state}")
        plan = json.loads((job.run_dir / "edit-plan.json").read_text())
        choreography = plan.get("visual_choreography")
        if not isinstance(choreography, dict):
            raise RuntimeError("opening_candidates_require_edit_plan_v3_2")
        ranking = rank_opening_candidates(choreography.get("openings"))
        ranking_path = job.run_dir / "opening-ranking.json"
        ranking_path.write_text(json.dumps(ranking, indent=2, sort_keys=True) + "\n")
        selection_path = job.run_dir / "opening-selection.json"
        if selection_path.exists():
            return {**ranking, **json.loads(selection_path.read_text())}
        if ranking["status"] == "auto_selected":
            selection = {
                "status": "auto_selected",
                "selected_opening_id": ranking["selected_opening_id"],
                "reason": ranking["reason"],
            }
            selection_path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")
            self.manager.receipt(
                job_id,
                "opening_auto_selected",
                opening_id=selection["selected_opening_id"],
                score_gap=ranking["score_gap"],
            )
            return {**ranking, **selection}
        if job.state is JobState.COMPILING:
            self.manager.transition(job_id, JobState.AWAITING_OPENING_SELECTION)
        self.manager.receipt(
            job_id,
            "opening_selection_requested",
            reason=ranking["reason"],
            score_gap=ranking["score_gap"],
        )
        return ranking

    def select_opening(self, job_id: str, opening_id: str, *, reason: str) -> dict[str, Any]:
        job = self.manager.load(job_id)
        if job.state is not JobState.AWAITING_OPENING_SELECTION:
            raise RuntimeError(f"job_not_awaiting_opening_selection:{job.state}")
        if not reason.strip():
            raise ValueError("opening_selection_reason_required")
        ranking = self.opening_candidates(job_id)
        valid_ids = {str(row["opening_id"]) for row in ranking["candidates"]}
        if opening_id not in valid_ids:
            raise ValueError("opening_selection_unknown_candidate")
        selection = {
            "status": "manually_selected",
            "selected_opening_id": opening_id,
            "reason": reason.strip(),
        }
        job.run_dir.joinpath("opening-selection.json").write_text(
            json.dumps(selection, indent=2, sort_keys=True) + "\n"
        )
        self.manager.receipt(
            job_id,
            "opening_manually_selected",
            opening_id=opening_id,
            reason=reason.strip(),
        )
        updated = self.manager.transition(job_id, JobState.COMPILING)
        return {**self._job_payload(updated), "opening_selection": {**ranking, **selection}}

    def finalize(self, job_id: str) -> dict[str, Any]:
        self._recover_stale_finalize_claim(job_id)
        plan_path = self.manager.load(job_id).run_dir / "edit-plan.json"
        if plan_path.exists():
            plan = json.loads(plan_path.read_text())
            if plan.get("schema_version") in {
                "edit-plan-v3.2",
                "edit-plan-v3.3",
                "edit-plan-v3.4",
                "edit-plan-v3.5",
                "edit-plan-v3.6",
            }:
                selection = plan_path.parent / "opening-selection.json"
                if not selection.exists():
                    ranking = self.opening_candidates(job_id)
                    if ranking["status"] == "selection_required":
                        raise RuntimeError("opening_selection_required_before_finalize")
        job = self.manager.claim_finalize(job_id)
        try:
            self._launch_worker("finalize", job_id)
        except Exception:
            self.manager.release_finalize_claim(job_id)
            raise
        return {**self._job_payload(job), "worker": "started"}

    def submit_review(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Record independent proof and mechanically promote or reopen the run."""

        job = self.manager.load(job_id)
        if job.state is not JobState.AWAITING_INDEPENDENT_REVIEW:
            raise RuntimeError(f"job_not_awaiting_independent_review:{job.state}")
        attempts = sorted(
            (job.run_dir / "work").glob("attempt-*"),
            key=lambda path: int(path.name.rsplit("-", 1)[-1]),
        )
        if not attempts:
            raise RuntimeError("review_attempt_missing")
        attempt = attempts[-1]
        written = write_review_submission(attempt, payload)
        qa_path = attempt / "qa.json"
        if not qa_path.is_file():
            raise RuntimeError("review_attempt_qa_missing")
        qa = json.loads(qa_path.read_text())
        self.manager.receipt(
            job_id,
            "independent_review_submitted",
            attempt=attempt.name,
            artifacts=written,
        )
        self.manager.transition(job_id, JobState.VERIFYING)
        result = self.manager.record_verification(
            job_id,
            attempt=attempt,
            gates=dict(qa.get("gates", {})),
            blockers=list(qa.get("blockers", [])),
        )
        return self._job_payload(result)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self.manager.load(job_id)
        if job.state in {
            JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE,
            JobState.COMPLETED,
            JobState.BLOCKED,
            JobState.CANCELLED,
        }:
            return self._job_payload(job)
        self._terminate_worker(job_id)
        return self._job_payload(self.manager.cancel(job_id))

    def support_bundle(self, job_id: str, output: str | None = None) -> dict[str, Any]:
        job = self.manager.load(job_id)
        path = Path(output).expanduser().resolve() if output else job.run_dir / "support.tar.gz"
        create_support_bundle(job.run_dir, path)
        return {"job_id": job_id, "bundle": str(path), "media_included": False}

    def repair_captions(self, job_id: str) -> dict[str, Any]:
        return repair_captions(root=self.canonical_root, manager=self.manager, job_id=job_id)

    def repair_privacy(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return repair_short_privacy(
            root=self.canonical_root,
            manager=self.manager,
            job_id=job_id,
            payload=payload,
        )

    def record_feedback(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        job = self.manager.load(job_id)
        if (
            job.state is JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE
            and payload.get("verdict") in {"approved", "approved_after_repair"}
            and payload.get("schema_version") != "owner-verdict-v2"
        ):
            raise ValueError("owner_verdict_v2_required_for_profile_v2_candidate")
        result = record_owner_feedback(job.run_dir, job_id, payload)
        feedback = result["feedback"]
        if feedback["verdict"] == "changes_requested":
            reason = str(feedback.get("summary", "")).strip()
            if not reason:
                reason = "; ".join(
                    str(issue["desired_correction"])
                    for issue in feedback.get("issues", [])
                )
            reopened = self.manager.request_owner_repair(job_id, reason=reason)
            result["job"] = self._job_payload(reopened)
        elif feedback["verdict"] in {"approved", "approved_after_repair"}:
            current = self.manager.load(job_id)
            if current.state is JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE:
                completed = self.manager.record_owner_approval(job_id)
                result["job"] = self._job_payload(completed)
        return result

    def sync_doctor(self) -> dict[str, Any]:
        commit = _git_commit(self.canonical_root)
        surface_commit = canonical_surface_commit(self.canonical_root)
        installed: dict[str, dict[str, Any]] = {}
        for path in (
            Path.home() / ".claude" / "skills" / "eddy",
            Path.home() / ".codex" / "skills" / "eddy",
            Path.home() / ".agents" / "skills" / "eddy",
        ):
            installed[str(path)] = {
                "exists": path.exists(),
                "is_symlink": path.is_symlink(),
                "target": str(path.resolve()) if path.exists() else None,
                "canonical": path.exists() and path.resolve() == self.canonical_root,
            }
        projections: dict[str, dict[str, Any]] = {}
        for relative in ("plugins/eddy/skills/eddy", "integrations/claude-code/skills/eddy"):
            path = self.canonical_root / relative
            if not path.exists():
                projections[relative] = {"exists": False, "ok": False}
                continue
            result = check_projection(
                self.canonical_root,
                path,
                files=CANONICAL_SURFACES,
                canonical_commit=surface_commit,
            )
            projections[relative] = {
                "exists": True,
                "ok": result.ok,
                "missing": list(result.missing),
                "changed": list(result.changed),
                "extra": list(result.extra),
                "manifest_commit_matches": result.manifest_commit_matches,
            }
        return {
            "product": canonical_contract().product_name,
            "canonical_root": str(self.canonical_root),
            "canonical_commit": commit,
            "canonical_surface_commit": surface_commit,
            "owner_channel": "main",
            "public_channel": "stable_tags",
            "installed": installed,
            "projections": projections,
            "owner_plugin": owner_plugin_status(self.canonical_root),
            "trust": trust_status(
                self.canonical_root / "dogfood" / "trust-ledger.json",
                runs_root=self.manager.runs_root,
            ),
        }

    def _launch_worker(self, action: str, job_id: str) -> None:
        job = self.manager.load(job_id)
        log_path = job.run_dir / f"worker-{action}.log"
        environment = os.environ.copy()
        source_root = self.canonical_root / "src"
        environment["PYTHONPATH"] = str(source_root) + os.pathsep + environment.get("PYTHONPATH", "")
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "eddy.worker",
                    action,
                    "--runs-root",
                    str(self.manager.runs_root),
                    "--canonical-root",
                    str(self.canonical_root),
                    "--job-id",
                    job_id,
                ],
                cwd=self.canonical_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        _ = process.pid

    def _terminate_worker(self, job_id: str) -> None:
        job = self.manager.load(job_id)
        for path in job.run_dir.glob("worker-*.json"):
            try:
                payload = json.loads(path.read_text())
                pid = int(payload["pid"])
                command = _worker_command_line(pid)
                if "eddy.worker" not in command or job_id not in command:
                    continue
                _terminate_process_tree(pid)
            except (json.JSONDecodeError, KeyError, OSError, ValueError):
                continue

    def _recover_stale_finalize_claim(self, job_id: str) -> None:
        job = self.manager.load(job_id)
        claim = job.run_dir / "finalize.claim"
        if not claim.exists():
            return
        marker = job.run_dir / "worker-finalize.json"
        if marker.exists():
            try:
                pid = int(json.loads(marker.read_text())["pid"])
                command = _worker_command_line(pid)
            except (json.JSONDecodeError, KeyError, OSError, ValueError):
                command = ""
            if "eddy.worker" in command and job_id in command:
                return
            marker.unlink(missing_ok=True)
            claim.unlink(missing_ok=True)
            return
        if time.time() - claim.stat().st_mtime > 60:
            claim.unlink(missing_ok=True)

    def _job_payload(self, job: Any) -> dict[str, Any]:
        owner_approved = _owner_approved(
            self.canonical_root / "dogfood" / "trust-ledger.json", job.id
        ) or _run_owner_approved(job.run_dir)
        if job.state is JobState.PROOF_GATED_CANDIDATE_AWAITING_OWNER_TASTE:
            proof_state = "proof_gated_candidate_awaiting_owner_taste"
            owner_approved = False
        elif job.state is JobState.COMPLETED and owner_approved:
            proof_state = "owner_taste_approved"
        elif job.state is JobState.COMPLETED:
            proof_state = "legacy_final_qa_passed"
        elif job.state is JobState.BLOCKED and (job.run_dir / "quarantine").exists():
            proof_state = "quarantined"
        elif job.state is JobState.BLOCKED:
            proof_state = "blocked_before_candidate"
        else:
            proof_state = "candidate"
        return {
            "job_id": job.id,
            "state": job.state.value,
            "source": str(job.source),
            "snapshot": str(job.snapshot),
            "run_dir": str(job.run_dir),
            "blockers": list(job.blockers),
            "proof_state": proof_state,
            "owner_approved": owner_approved,
        }


def _git_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def _owner_approved(ledger: Path, job_id: str) -> bool:
    if not ledger.exists():
        return False
    try:
        payload = json.loads(ledger.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return any(
        row.get("id") == job_id and row.get("owner_approved") is True
        for row in payload.get("runs", [])
        if isinstance(row, dict)
    )


def _run_owner_approved(run_dir: Path) -> bool:
    verdict = run_dir / "review" / "owner-verdict.json"
    if not verdict.is_file():
        return False
    try:
        payload = json.loads(verdict.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return (
        payload.get("schema_version") == "owner-verdict-v2"
        and payload.get("verdict") in {"approved", "approved_after_repair"}
    )
