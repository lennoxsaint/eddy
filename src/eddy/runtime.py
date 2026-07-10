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

from .plan import EditPlanV3, PlanValidationError


class JobState(StrEnum):
    QUEUED = "queued"
    PREFLIGHTING = "preflighting"
    AWAITING_HOST_PLAN = "awaiting_host_plan"
    COMPILING = "compiling"
    RENDERING_PROXY = "rendering_proxy"
    ENHANCING_AUDIO = "enhancing_audio"
    RENDERING_FINAL = "rendering_final"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


TERMINAL_STATES = {JobState.COMPLETED, JobState.BLOCKED, JobState.CANCELLED}


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    source: Path
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
        hashes = {str(path): _sha256(path) for path in media}
        _write_json(run_dir / "source-lock.json", {"before": hashes, "after": None})
        job = Job(job_id, source, run_dir, JobState.QUEUED)
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
            run_dir=Path(payload["run_dir"]),
            state=JobState(payload["state"]),
            blockers=tuple(payload.get("blockers", [])),
        )

    def submit_plan(self, job_id: str, payload: dict[str, Any]) -> Job:
        job = self.load(job_id)
        if job.state is not JobState.AWAITING_HOST_PLAN:
            raise RuntimeError(f"job_not_awaiting_host_plan:{job.state}")
        plan = EditPlanV3.from_dict(payload)
        lock = json.loads((job.run_dir / "source-lock.json").read_text())
        if plan.source_hashes != lock["before"]:
            raise PlanValidationError("edit_plan_source_hash_mismatch")
        _write_json(job.run_dir / "edit-plan.json", plan.to_dict())
        updated = Job(job.id, job.source, job.run_dir, JobState.COMPILING)
        self._save(updated)
        _receipt(updated, "host_plan_accepted")
        return updated

    def transition(self, job_id: str, state: JobState) -> Job:
        job = self.load(job_id)
        if job.state in TERMINAL_STATES:
            raise RuntimeError(f"terminal_job_cannot_transition:{job.state}")
        updated = Job(job.id, job.source, job.run_dir, state, job.blockers)
        self._save(updated)
        _receipt(updated, "job_state_changed", state=state.value)
        return updated

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
        after = {str(path): _sha256(path) for path in _source_files(job.source)}
        source_lock["after"] = after
        _write_json(job.run_dir / "source-lock.json", source_lock)
        source_green = after == source_lock["before"]
        verified_gates = {**gates, "source_lock": source_green and gates.get("source_lock", True)}
        verified_blockers = list(dict.fromkeys(blockers + ([] if source_green else ["source_hash_changed"])))
        _write_json(
            job.run_dir / "verification.json",
            {"gates": verified_gates, "blockers": verified_blockers},
        )

        if all(verified_gates.values()) and not verified_blockers:
            final = job.run_dir / "final"
            if final.exists():
                raise RuntimeError("final_already_exists")
            shutil.move(str(attempt), str(final))
            updated = Job(job.id, job.source, job.run_dir, JobState.COMPLETED)
            _receipt(updated, "proof_gated_edit_completed")
        else:
            quarantine = job.run_dir / "quarantine" / attempt.name
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            if quarantine.exists():
                raise RuntimeError(f"quarantine_attempt_exists:{attempt.name}")
            shutil.move(str(attempt), str(quarantine))
            updated = Job(
                job.id,
                job.source,
                job.run_dir,
                JobState.BLOCKED,
                tuple(verified_blockers),
            )
            _receipt(
                updated,
                "blocked_attempt_quarantined",
                blockers=verified_blockers,
                quarantine=str(quarantine),
            )
        self._save(updated)
        return updated

    def cancel(self, job_id: str) -> Job:
        job = self.load(job_id)
        if job.state in TERMINAL_STATES:
            return job
        cancelled = Job(job.id, job.source, job.run_dir, JobState.CANCELLED)
        self._save(cancelled)
        _receipt(cancelled, "job_cancelled")
        return cancelled

    def _save(self, job: Job) -> None:
        _write_json(
            job.run_dir / "state.json",
            {
                "id": job.id,
                "source": str(job.source),
                "run_dir": str(job.run_dir),
                "state": job.state.value,
                "blockers": list(job.blockers),
            },
        )


def _source_files(source: Path) -> list[Path]:
    allowed = {".mp4", ".mov", ".mkv", ".webm", ".wav", ".m4a", ".mp3"}
    if source.is_file():
        return [source] if source.suffix.lower() in allowed else []
    return sorted(path for path in source.rglob("*") if path.is_file() and path.suffix.lower() in allowed)


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
