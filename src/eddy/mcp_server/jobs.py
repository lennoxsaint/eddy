"""Subprocess job manager for the MCP server.

Long Eddy operations run as child `eddy` CLI processes (``python -m eddy …``) with ``EDDY_NO_ANIM=1``
so their output is clean. We never block on them: `start_*` returns immediately with a job id, and
`status()` derives state from the child's exit code plus the run's on-disk ``state.json`` — so status
is robust even across a server restart (the run dir is the source of truth). The job id is the run
slug for single-run kinds, which makes the run dir deterministic (``runs_dir/<slug>``).

`spawn` is injectable so tests exercise the manager without launching real processes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eddy.config import load_config
from eddy.runs import default_slug

SpawnFn = Callable[[list[str], Path, dict[str, str]], Any]


def _default_spawn(argv: list[str], log_path: Path, env: dict[str, str]) -> Any:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Popen dup()s the fd, so the local handle can be dropped right after; we close it once Popen has
    # its own copy (refcount drop would do it on CPython, but be explicit so it's correct everywhere).
    with open(log_path, "w") as fh:
        return subprocess.Popen(argv, stdout=fh, stderr=subprocess.STDOUT, env=env, text=True)


def _tail(path: Path, lines: int = 40) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


@dataclass
class Job:
    id: str
    kind: str
    argv: list[str]
    run_dir: Path | None
    log_path: Path
    proc: Any  # Popen-like: poll() / terminate() / pid


def _flag3(args: list[str], name: str, value: bool | None) -> None:
    """Append a 3-state --x/--no-x flag only when explicitly set (None = inherit profile/default)."""
    if value is True:
        args.append(f"--{name}")
    elif value is False:
        args.append(f"--no-{name}")


class JobManager:
    """Tracks child `eddy` processes and reports their status from exit code + on-disk run state."""

    def __init__(self, runs_dir: Path | None = None, spawn: SpawnFn | None = None) -> None:
        self.runs_dir = Path(runs_dir) if runs_dir else load_config().runs_dir
        self._spawn = spawn or _default_spawn
        self._jobs: dict[str, Job] = {}

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["EDDY_NO_ANIM"] = "1"  # the child must not animate; keep its output clean
        return env

    def _eddy(self, *args: str) -> list[str]:
        # use THIS interpreter's eddy, not whatever `eddy` happens to be on PATH
        return [sys.executable, "-m", "eddy", *args]

    def _is_live(self, jid: str) -> bool:
        job = self._jobs.get(jid)
        return job is not None and job.proc.poll() is None

    def _free_slug(self, base: str) -> str:
        """Pick a slug whose run isn't already being written by a live job (avoids two `eddy`
        processes writing the same run dir, which would corrupt state.json/iterations)."""
        slug, n = base, 2
        while self._is_live(slug):
            slug, n = f"{base}-{n}", n + 1
        return slug

    def _launch(self, jid: str, kind: str, args: list[str], run_dir: Path | None) -> Job:
        # Refuse to overwrite a still-running job of the same id — it would orphan the first child
        # (untracked, uncancellable) and risk concurrent writes to one run dir.
        if self._is_live(jid):
            raise RuntimeError(f"job {jid!r} is already running; cancel it or wait before starting again")
        argv = self._eddy(*args)
        log_path = self.runs_dir / ".mcp-jobs" / f"{jid}.log"
        proc = self._spawn(argv, log_path, self._env())
        job = Job(id=jid, kind=kind, argv=argv, run_dir=run_dir, log_path=log_path, proc=proc)
        self._jobs[jid] = job
        return job

    # --- starters ---------------------------------------------------------------------------------
    def start_run(
        self,
        source: str,
        *,
        slug: str | None = None,
        target_minutes: float | None = None,
        language: str | None = None,
        fmt: str | None = None,
        profile: str | None = None,
        local_only: bool = False,
        skip_shorts: bool | None = None,
        skip_package: bool | None = None,
    ) -> Job:
        slug = self._free_slug(slug or default_slug(Path(source)))
        args = ["run", str(source), "--slug", slug]
        if target_minutes is not None:
            args += ["--target-minutes", str(target_minutes)]
        if language:
            args += ["--language", language]
        if fmt:
            args += ["--format", fmt]
        if profile:
            args += ["--profile", profile]
        if local_only:
            args.append("--local-only")
        _flag3(args, "skip-shorts", skip_shorts)
        _flag3(args, "skip-package", skip_package)
        return self._launch(slug, "run", args, self.runs_dir / slug)

    def start_shorts(self, source: str, *, slug: str | None = None, language: str | None = None) -> Job:
        slug = self._free_slug(slug or default_slug(Path(source)))
        args = ["shorts", str(source), "--slug", slug]
        if language:
            args += ["--language", language]
        return self._launch(slug, "shorts", args, self.runs_dir / slug)

    def start_transcribe(self, source: str, *, slug: str | None = None, language: str | None = None) -> Job:
        slug = self._free_slug(slug or default_slug(Path(source)))
        args = ["transcribe", str(source), "--slug", slug]
        if language:
            args += ["--language", language]
        return self._launch(slug, "transcribe", args, self.runs_dir / slug)

    def start_render(self, run_dir: str, *, proxy: bool = False) -> Job:
        rd = Path(run_dir)
        args = ["render", str(rd)]
        if proxy:
            args.append("--proxy")
        return self._launch(rd.name, "render", args, rd)

    def start_batch(self, path: str, *, skip_shorts: bool = False, skip_package: bool = False) -> Job:
        jid = f"batch-{Path(path).name}"
        args = ["batch", str(path), "--json"]
        if skip_shorts:
            args.append("--skip-shorts")
        if skip_package:
            args.append("--skip-package")
        return self._launch(jid, "batch", args, None)

    # --- inspection -------------------------------------------------------------------------------
    def _phase(self, run_dir: Path | None) -> str | None:
        if not run_dir:
            return None
        sj = run_dir / "state.json"
        if not sj.exists():
            return None
        try:
            return json.loads(sj.read_text()).get("phase")
        except (OSError, json.JSONDecodeError):
            return None

    def status(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        run_dir = job.run_dir if job else (self.runs_dir / job_id)
        phase = self._phase(run_dir)
        if job is None:
            # unknown to this server instance (e.g. restarted) — infer purely from disk
            if phase is not None:
                state = "completed" if phase == "done" else "interrupted"
                return {"job_id": job_id, "state": state, "phase": phase, "run_dir": str(run_dir)}
            return {"job_id": job_id, "state": "unknown"}
        rc = job.proc.poll()
        state = "running" if rc is None else ("completed" if rc == 0 else "failed")
        out: dict[str, Any] = {
            "job_id": job_id,
            "kind": job.kind,
            "state": state,
            "returncode": rc,
            "phase": phase,
            "run_dir": str(run_dir) if run_dir else None,
            "pid": getattr(job.proc, "pid", None),
        }
        if state == "failed":
            out["log_tail"] = _tail(job.log_path)
        return out

    def cancel(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            return {"job_id": job_id, "cancelled": False, "reason": "unknown job"}
        if job.proc.poll() is None:
            job.proc.terminate()
            return {"job_id": job_id, "cancelled": True}
        return {"job_id": job_id, "cancelled": False, "reason": "already finished"}

    def list(self) -> list[dict]:
        return [self.status(jid) for jid in self._jobs]
