"""The TUI's bridge to Eddy's data + actions.

Reads come straight from disk (`list_runs`, `state.json`, `final/`); long actions go through the
shared `JobManager` (subprocess, non-blocking). `execute()` dispatches the mutating intents; read/UI
intents (doctor, runs, open, help, quit) are handled by the app. `JobManager.spawn` is injectable, so
the whole TUI is testable without launching real `eddy` processes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from eddy.batch import list_runs
from eddy.config import load_config
from eddy.jobs import JobManager, _tail
from eddy.tui.intents import Intent

_ERR_LINE = re.compile(r"([A-Za-z_]\w*(?:Error|Exception)):\s*(.*)")
_MAX_TEXT = 20_000
# extensions we can usefully show as text in the preview modal; everything else (video, images,
# audio) is a binary the creator opens in their player / image viewer.
_TEXT_EXTS = {".md", ".txt", ".srt", ".vtt", ".json", ".edl", ".ffconcat", ".csv"}


def run_verdict(state: dict) -> str | None:
    """A plain, non-technical quality verdict from a run's state — or None when there's nothing to say
    yet (no attempts). Deliberately avoids fabricating a quality band; it speaks in passes + outcome."""
    attempts = state.get("attempts") or []
    if not attempts:
        return None
    n = len(attempts)
    last = attempts[-1]
    if state.get("phase") == "done":
        return f"Kept the best of {n} editing passes." if n > 1 else "Edited in a single clean pass."
    tail = " — looking good" if last.get("gates_passed") else " — refining"
    return f"Editing pass {last.get('iteration', n)}{tail}"


def local_provider() -> Any:
    """The LOCAL brain (Ollama) for interpreting natural-language input — never a cloud provider, so a
    typed sentence can't silently bill an API call. Returns None if no local brain is available (the
    caller then degrades gracefully)."""
    try:
        from eddy.providers.base import get_provider

        return get_provider(load_config(), name="ollama")
    except Exception:
        return None


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

    def artifacts(self, slug: str) -> list[dict]:
        """Everything in a run's final/ as {name, kind('text'|'binary'|'folder'), size}. Powers the
        in-app preview so a creator can validate the launch kit without an OS file manager."""
        final = self.run_dir(slug) / "final"
        out: list[dict] = []
        if not final.exists():
            return out
        for p in sorted(final.iterdir()):
            if p.is_dir():
                try:
                    n = sum(1 for _ in p.iterdir())
                except OSError:
                    n = 0
                out.append({"name": p.name + "/", "kind": "folder", "size": n})
            else:
                kind = "text" if p.suffix.lower() in _TEXT_EXTS else "binary"
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                out.append({"name": p.name, "kind": kind, "size": size})
        return out

    def brain_label(self) -> str:
        active = getattr(self.cfg.provider, "active", "?")
        try:
            from eddy.privacy import is_offline

            tag = " · offline" if is_offline() else ""
        except Exception:
            tag = ""
        return f"{active}{tag}"

    def edit_options(self, source: str, focus: str | None = None) -> dict:
        """Plain-English edit path choices for the TUI. Fake test configs skip live detection."""
        if not all(hasattr(self.cfg, attr) for attr in ("loop", "provider")):
            return {"requires_choice": False, "selected_option_id": None, "options": []}
        try:
            from eddy.doctor import detect
            from eddy.edit_options import edit_path_options

            return edit_path_options(
                detect(),
                source=source,
                focus=focus,
                host_agent_available=False,
                cost_cap_usd=float(getattr(self.cfg.loop, "max_run_cost_usd", 0.0) or 0.0),
            )
        except Exception:
            return {"requires_choice": False, "selected_option_id": None, "options": []}

    def jobs_status(self) -> list[dict]:
        return self.jobs.list()

    def any_running(self) -> bool:
        return any(j.get("state") == "running" for j in self.jobs.list())

    def failed_jobs(self) -> list[dict]:
        """Finished jobs that exited non-zero (each status carries a `log_tail`)."""
        return [j for j in self.jobs.list() if j.get("state") == "failed"]

    def log_tail(self, slug: str, lines: int = 12) -> str:
        """The last lines of a job's live log (runs_dir/.mcp-jobs/<slug>.log), '' if none yet."""
        return _tail(self.cfg.runs_dir / ".mcp-jobs" / f"{slug}.log", lines)

    def is_interrupted(self, slug: str) -> bool:
        """A run with progress but neither finished nor currently live (resumable via `render`)."""
        st = self.jobs.status(slug)
        return st.get("state") == "interrupted"

    def failure_detail(self, slug: str) -> dict | None:
        """Plain-language failure summary for a run that errored, or None if it didn't fail.

        The `eddy` subprocess already prints a friendly block (via errors.friendly_error) into its
        log: `✗ headline / → next step / crash log: path`. We prefer that verbatim — it IS the
        friendly mapping. If the child died before printing one (killed/segfault), we fall back to
        mapping the last `…Error:` line in the log through errors.friendly_by_name. Always returns a
        log tail so there's something concrete to read."""
        log_path = self.cfg.runs_dir / ".mcp-jobs" / f"{slug}.log"
        text = log_path.read_text(errors="replace") if log_path.exists() else ""
        failed = self.jobs.status(slug).get("state") == "failed" or "✗ " in text or "Traceback (most recent call last)" in text
        if not failed:
            return None
        headline = next_step = crash_log = ""
        for ln in text.splitlines():
            s = ln.strip()
            if s.startswith("✗ ") and not headline:
                headline = s[2:].strip()
            elif s.startswith("→ ") and not next_step:
                next_step = s[2:].strip()
            elif s.startswith("crash log:"):
                crash_log = s.split("crash log:", 1)[1].strip()
        if not headline:  # no friendly block printed — map the raw error class ourselves
            from eddy.errors import friendly_by_name

            cls, msg = "Error", "the run ended unexpectedly — see the log below"
            for ln in reversed(text.splitlines()):
                m = _ERR_LINE.search(ln)
                if m:
                    cls, msg = m.group(1), m.group(2)
                    break
            headline, next_step = friendly_by_name(cls, msg)
        return {
            "slug": slug,
            "headline": headline,
            "next_step": next_step or "Run `eddy doctor`, or re-run once the issue is fixed.",
            "crash_log": crash_log,
            "tail": _tail(log_path, 20),
        }

    # --- side-effecting helpers -------------------------------------------------------------------
    def cancel(self, slug: str) -> dict:
        """Stop a running job (delegates to JobManager.cancel)."""
        return self.jobs.cancel(slug)

    def results_path(self, slug: str) -> Path | None:
        """The folder a reveal would open (final/ if present, else the run dir), or None if neither
        exists. Lets the UI show an honest, copyable path when no OS opener is available."""
        for target in (self.run_dir(slug) / "final", self.run_dir(slug)):
            if target.exists():
                return target
        return None

    def reveal(self, slug: str) -> bool:
        """Open a run's results in the OS file manager (final/ if present, else the run dir). Returns
        False if there's nothing to show or no opener. This is a LOCAL folder reveal, not a URL."""
        target = self.results_path(slug)
        if target is None:
            return False
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            elif sys.platform.startswith("win"):
                import os

                os.startfile(str(target))  # type: ignore[attr-defined]  # Windows-only
            else:
                opener = shutil.which("xdg-open")
                if not opener:
                    return False
                subprocess.Popen([opener, str(target)])
            return True
        except Exception:
            return False

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
                    focus=intent.args.get("focus"),
                    focus_mode=intent.args.get("focus_mode"),
                    edit_path=intent.args.get("edit_path"),
                    auto_fallback=bool(intent.args.get("auto_fallback", True)),
                    skip_shorts=intent.args.get("skip_shorts"),
                    skip_package=intent.args.get("skip_package"),
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
