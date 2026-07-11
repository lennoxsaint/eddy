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
from .editorial import validate_editorial_review


class JobState(StrEnum):
    QUEUED = "queued"
    PREFLIGHTING = "preflighting"
    AWAITING_HOST_PLAN = "awaiting_host_plan"
    AWAITING_HOST_REPAIR = "awaiting_host_repair"
    COMPILING = "compiling"
    RENDERING_PROXY = "rendering_proxy"
    ENHANCING_AUDIO = "enhancing_audio"
    RENDERING_FINAL = "rendering_final"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


TERMINAL_STATES = {JobState.COMPLETED, JobState.BLOCKED, JobState.CANCELLED}
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
    "shorts_contextual_motion",
    *(f"hyperframes_motion_hook_{rank}" for rank in range(1, 4)),
    *(f"contextual_motion_hook_{rank}" for rank in range(1, 4)),
    *(f"descript_effect_survival_hook_{rank}" for rank in range(1, 4)),
    *(f"deterministic_qa_hook_{rank}" for rank in range(1, 4)),
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
        lock = json.loads((job.run_dir / "source-lock.json").read_text())
        if plan.source_hashes != lock["before"]:
            raise PlanValidationError("edit_plan_source_hash_mismatch")
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
        _receipt(updated, "host_plan_accepted")
        return updated

    def transition(self, job_id: str, state: JobState) -> Job:
        job = self.load(job_id)
        if job.state in TERMINAL_STATES:
            raise RuntimeError(f"terminal_job_cannot_transition:{job.state}")
        updated = Job(job.id, job.source, job.snapshot, job.run_dir, state, job.blockers)
        self._save(updated)
        _receipt(updated, "job_state_changed", state=state.value)
        return updated

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
        missing_gates = sorted(REQUIRED_FINAL_GATES - set(verified_gates))
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
            _write_json(attempt / "artifact-manifest.json", {"files": _artifact_hashes(attempt)})
            final = job.run_dir / "final"
            if final.exists():
                raise RuntimeError("final_already_exists")
            shutil.move(str(attempt), str(final))
            updated = Job(job.id, job.source, job.snapshot, job.run_dir, JobState.COMPLETED)
            _receipt(updated, "proof_gated_edit_completed")
        else:
            quarantine = job.run_dir / "quarantine" / attempt.name
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            if quarantine.exists():
                raise RuntimeError(f"quarantine_attempt_exists:{attempt.name}")
            shutil.move(str(attempt), str(quarantine))
            attempt_number = _attempt_number(attempt.name)
            remaining_attempts = max(0, 3 - attempt_number)
            _write_json(
                job.run_dir / "repair-packet.json",
                {
                    "schema_version": "eddy-repair-packet-v1",
                    "attempt": attempt_number,
                    "remaining_attempts": remaining_attempts,
                    "gates": verified_gates,
                    "blockers": verified_blockers,
                    "quarantine": str(quarantine),
                },
            )
            next_state = JobState.AWAITING_HOST_REPAIR if remaining_attempts else JobState.BLOCKED
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
                "host_repair_requested" if remaining_attempts else "blocked_attempt_quarantined",
                blockers=verified_blockers,
                quarantine=str(quarantine),
                remaining_attempts=remaining_attempts,
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
