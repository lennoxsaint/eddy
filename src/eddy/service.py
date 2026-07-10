"""Public service boundary shared by CLI and MCP adapters."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .contract import canonical_contract
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

    def edit_options(self, source: str, *, format: str = "youtube") -> dict[str, Any]:
        path = Path(source).expanduser().resolve()
        if format != "youtube":
            raise ValueError(f"unsupported_format:{format}")
        if not path.exists():
            raise FileNotFoundError(f"source_not_found:{path}")
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
        }

    def edit_start(self, source: str, *, format: str = "youtube") -> dict[str, Any]:
        self.edit_options(source, format=format)
        job = self.manager.start(Path(source))
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
        return {
            "schema_version": "eddy-host-packet-v3",
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
                },
                "shorts": {
                    "minimum_screen_share": 0.25,
                    "minimum_animated_beats": 2,
                    "hook_beat_starts_by_s": 2.0,
                }
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
            "edit_plan_schema": "edit-plan-v3",
            "requirements": {
                "primary_hooks": 1,
                "alternate_hooks": 2,
                "shared_body": True,
                "packaging": False,
            },
        }

    def host_submit(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._job_payload(self.manager.submit_plan(job_id, payload))

    def finalize(self, job_id: str) -> dict[str, Any]:
        self._recover_stale_finalize_claim(job_id)
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
