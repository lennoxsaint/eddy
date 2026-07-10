"""Public service boundary shared by CLI and MCP adapters."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .contract import canonical_contract
from .runtime import JobManager, JobState
from .sync import CANONICAL_SURFACES, check_projection
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
        return {
            "schema_version": "eddy-host-packet-v3",
            "job_id": job.id,
            "state": job.state.value,
            "source_hashes": source_lock["before"],
            "transcript": json.loads(transcript_path.read_text()) if transcript_path.exists() else None,
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
        job = self.manager.load(job_id)
        if job.state is not JobState.COMPILING:
            raise RuntimeError(f"job_not_compiled:{job.state}")
        self._launch_worker("finalize", job_id)
        return {**self._job_payload(job), "worker": "started"}

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self._job_payload(self.manager.cancel(job_id))

    def support_bundle(self, job_id: str, output: str | None = None) -> dict[str, Any]:
        job = self.manager.load(job_id)
        path = Path(output).expanduser().resolve() if output else job.run_dir / "support.tar.gz"
        create_support_bundle(job.run_dir, path)
        return {"job_id": job_id, "bundle": str(path), "media_included": False}

    def sync_doctor(self) -> dict[str, Any]:
        commit = _git_commit(self.canonical_root)
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
            result = check_projection(self.canonical_root, path, files=CANONICAL_SURFACES)
            projections[relative] = {
                "exists": True,
                "ok": result.ok,
                "missing": list(result.missing),
                "changed": list(result.changed),
            }
        return {
            "product": canonical_contract().product_name,
            "canonical_root": str(self.canonical_root),
            "canonical_commit": commit,
            "owner_channel": "main",
            "public_channel": "stable_tags",
            "installed": installed,
            "projections": projections,
            "trust": trust_status(self.canonical_root / "dogfood" / "trust-ledger.json"),
        }

    def _launch_worker(self, action: str, job_id: str) -> None:
        job = self.manager.load(job_id)
        log_path = job.run_dir / f"worker-{action}.log"
        environment = os.environ.copy()
        source_root = self.canonical_root / "src"
        environment["PYTHONPATH"] = str(source_root) + os.pathsep + environment.get("PYTHONPATH", "")
        with log_path.open("ab") as log:
            subprocess.Popen(
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

    @staticmethod
    def _job_payload(job: Any) -> dict[str, Any]:
        return {
            "job_id": job.id,
            "state": job.state.value,
            "source": str(job.source),
            "run_dir": str(job.run_dir),
            "blockers": list(job.blockers),
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
