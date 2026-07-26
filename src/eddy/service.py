"""Public service boundary shared by CLI and MCP adapters."""

from __future__ import annotations

import hashlib
import json
import os
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
from .quality import resolve_quality_profile
from .runtime import JobManager, JobState
from .sync import CANONICAL_SURFACES, canonical_surface_commit, check_projection
from .support import create_support_bundle
from .trust import trust_status


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
    ) -> dict[str, Any]:
        self.edit_options(source, format=format, profile_id=profile_id)
        profile, profile_path = resolve_quality_profile(
            self.canonical_root,
            explicit_profile_id=profile_id,
        )
        job = self.manager.start(Path(source))
        source_lock = json.loads((job.run_dir / "source-lock.json").read_text())
        create_contract_bundle(
            job.run_dir,
            source=job.source,
            canonical_root=self.canonical_root,
            profile=profile,
            profile_path=profile_path,
            source_hashes=source_lock["before"],
        )
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
        bundle_path = job.run_dir / "contracts" / "contract-bundle.json"
        if not bundle_path.is_file():
            raise RuntimeError("contract_bundle_missing")
        bundle = json.loads(bundle_path.read_text())
        quality_profile_path = job.run_dir / str(bundle["profile"]["ref"])
        frame_path = job.run_dir / "frame.md"
        short_frame_path = job.run_dir / "shorts" / "frame.md"
        design_path = job.run_dir / "design.md"
        frame_sha256 = hashlib.sha256(frame_path.read_bytes()).hexdigest()
        short_frame_sha256 = hashlib.sha256(short_frame_path.read_bytes()).hexdigest()
        design_sha256 = hashlib.sha256(design_path.read_bytes()).hexdigest()
        bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        return {
            "schema_version": "eddy-host-packet-v3.1",
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
                        "pixel_faithful_demo",
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
            "edit_plan_schema": "edit-plan-v3.4",
            "accepted_edit_plan_schemas": [
                "edit-plan-v3",
                "edit-plan-v3.1",
                "edit-plan-v3.2",
                "edit-plan-v3.3",
                "edit-plan-v3.4",
            ],
            "frame_contract": {
                "schema_version": "eddy-project-frame-v2",
                "path": str(frame_path),
                "ref": "frame.md",
                "sha256": frame_sha256,
            },
            "design_contracts": {
                "design": {
                    "schema_version": "eddy-design-contract-v1",
                    "path": str(design_path),
                    "ref": "design.md",
                    "sha256": design_sha256,
                    "revision": bundle["design_contracts"]["design"]["revision"],
                },
                "long_frame": {
                    "schema_version": "eddy-project-frame-v2",
                    "path": str(frame_path),
                    "ref": "frame.md",
                    "sha256": frame_sha256,
                    "revision": bundle["design_contracts"]["long_frame"]["revision"],
                },
                "short_frame": {
                    "schema_version": "eddy-project-frame-v2",
                    "path": str(short_frame_path),
                    "ref": "shorts/frame.md",
                    "sha256": short_frame_sha256,
                    "revision": bundle["design_contracts"]["short_frame"]["revision"],
                },
            },
            "contract_bundle": {
                "schema_version": "eddy-contract-bundle-ref-v1",
                "path": str(bundle_path),
                "ref": "contracts/contract-bundle.json",
                "sha256": bundle_sha256,
            },
            "quality_profile": json.loads(quality_profile_path.read_text()),
            "audio_policy": bundle["audio_policy"],
            "caption_policy": json.loads(quality_profile_path.read_text())["captions"],
            "grade_policy": json.loads(quality_profile_path.read_text()).get("grade", {}),
            "completion_policy": json.loads(quality_profile_path.read_text()).get("review", {}),
            "requirements": {
                "primary_hooks": 1,
                "alternate_hooks": 2,
                "shared_body": True,
                "packaging": False,
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
            JobState.COMPLETED,
        }:
            raise RuntimeError(f"design_contract_revision_unavailable:{job.state}")
        if job.state is JobState.COMPLETED:
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
            if plan.get("schema_version") in {"edit-plan-v3.2", "edit-plan-v3.3"}:
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

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self.manager.load(job_id)
        if job.state in {JobState.COMPLETED, JobState.BLOCKED, JobState.CANCELLED}:
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
                command = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "command="],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout
                if "eddy.worker" not in command or job_id not in command:
                    continue
                os.killpg(pid, signal.SIGTERM)
            except (FileNotFoundError, json.JSONDecodeError, KeyError, ProcessLookupError, ValueError):
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
                command = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "command="],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                command = ""
            if "eddy.worker" in command and job_id in command:
                return
            marker.unlink(missing_ok=True)
            claim.unlink(missing_ok=True)
            return
        if time.time() - claim.stat().st_mtime > 60:
            claim.unlink(missing_ok=True)

    def _job_payload(self, job: Any) -> dict[str, Any]:
        if job.state is JobState.COMPLETED:
            proof_state = "final_qa_passed"
        elif job.state is JobState.BLOCKED and (job.run_dir / "quarantine").exists():
            proof_state = "quarantined"
        elif job.state is JobState.BLOCKED:
            proof_state = "blocked_before_candidate"
        else:
            proof_state = "candidate"
        owner_approved = _owner_approved(
            self.canonical_root / "dogfood" / "trust-ledger.json", job.id
        )
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
