"""The TUI's bridge to Eddy's data + actions.

Reads come straight from disk (`list_runs`, `state.json`, `final/`); long actions go through the
shared `JobManager` (subprocess, non-blocking). `execute()` dispatches the mutating intents; read/UI
intents (doctor, runs, open, help, quit) are handled by the app. `JobManager.spawn` is injectable, so
the whole TUI is testable without launching real `eddy` processes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eddy.batch import list_runs
from eddy.config import load_config
from eddy.jobs import JobManager
from eddy.tui.intents import Intent

_MAX_TEXT = 20_000


class TuiData:
    def __init__(self, jobs: JobManager | None = None, cfg: Any = None) -> None:
        self.cfg = cfg or load_config()
        self.jobs = jobs or JobManager(runs_dir=self.cfg.runs_dir)

    # --- reads ------------------------------------------------------------------------------------
    def runs(self) -> list[dict]:
        """Every run, newest first."""
        try:
            return list(reversed(list_runs(self.cfg.runs_dir)))
        except OSError:
            return []

    def run_dir(self, slug: str) -> Path:
        return self.cfg.runs_dir / slug

    def run_detail(self, slug: str) -> dict:
        rd = self.run_dir(slug)
        state: dict = {}
        sp = rd / "state.json"
        if sp.exists():
            try:
                state = json.loads(sp.read_text())
            except (OSError, json.JSONDecodeError):
                state = {}
        final = rd / "final"
        artifacts = sorted(p.name for p in final.iterdir()) if final.exists() else []
        return {"slug": slug, "run_dir": str(rd), "state": state, "artifacts": artifacts}

    def artifact_text(self, slug: str, name: str) -> str | None:
        p = self.run_dir(slug) / "final" / name
        if not p.exists():
            return None
        return p.read_text(errors="replace")[:_MAX_TEXT]

    def brain_label(self) -> str:
        active = getattr(self.cfg.provider, "active", "?")
        try:
            from eddy.privacy import is_offline

            tag = " · offline" if is_offline() else ""
        except Exception:
            tag = ""
        return f"{active}{tag}"

    def jobs_status(self) -> list[dict]:
        return self.jobs.list()

    def any_running(self) -> bool:
        return any(j.get("state") == "running" for j in self.jobs.list())

    # --- actions ----------------------------------------------------------------------------------
    def execute(self, intent: Intent) -> dict:
        """Dispatch a mutating intent. Returns a small result dict for the status line. UI-only intents
        (doctor/runs/open/help/quit) are handled by the app, not here."""
        a = intent.action
        if a in {"run", "shorts", "transcribe"}:
            src = str(Path(intent.args["source"]).expanduser())
            if a == "run":
                job = self.jobs.start_run(
                    src,
                    target_minutes=intent.args.get("target_minutes"),
                    local_only=bool(intent.args.get("local_only")),
                )
            elif a == "shorts":
                job = self.jobs.start_shorts(src)
            else:
                job = self.jobs.start_transcribe(src)
            return {"kind": "job", "job_id": job.id, "run_dir": str(job.run_dir), "msg": f"started {a} · {job.id}"}
        if a == "render":
            job = self.jobs.start_render(str(self.run_dir(intent.args["run"])))
            return {"kind": "job", "job_id": job.id, "msg": f"rendering · {job.id}"}
        if a == "clean":
            from eddy.clean import clean_run

            clean_run(self.run_dir(intent.args["run"]))
            return {"kind": "done", "msg": f"cleaned {intent.args['run']}"}
        if a == "purge":
            from eddy.clean import purge_run

            purge_run(self.run_dir(intent.args["run"]), full=bool(intent.args.get("full")))
            return {"kind": "done", "msg": f"purged {intent.args['run']}"}
        return {"kind": "noop", "msg": ""}
