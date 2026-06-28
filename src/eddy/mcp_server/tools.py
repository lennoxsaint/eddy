"""Tool implementations for the Eddy MCP server — plain functions returning JSON-able dicts.

Kept free of the MCP SDK so they're unit-testable on their own; `server.py` wires them to FastMCP.

Two rules make these safe inside a stdio server:
* **Reads run in-process** but under `_quiet()`, which redirects stdout to stderr — a stray `print`
  in any Eddy code path can never corrupt the JSON-RPC stream on stdout.
* **Long, mutating ops are jobs** (subprocess, via `JobManager`); destructive ops (clean, purge)
  refuse unless ``confirm=True``.
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager, redirect_stdout
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from eddy.config import load_config
from eddy.jobs import JobManager

_MAX_TEXT = 200_000  # cap on any single text artifact returned to a client

_jobs: JobManager | None = None


def jobs() -> JobManager:
    global _jobs
    if _jobs is None:
        _jobs = JobManager()
    return _jobs


@contextmanager
def _quiet() -> Iterator[None]:
    """Run an in-process Eddy call with its stdout redirected to stderr (protects the stdio protocol)."""
    with redirect_stdout(sys.stderr):
        yield


def _resolve_run(ref: str) -> Path:
    """A run reference is either an absolute/relative path or a bare slug under the runs dir."""
    p = Path(ref).expanduser()
    if p.exists():
        return p
    return load_config().runs_dir / ref


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(errors="replace")[:_MAX_TEXT]


# --- reads (in-process) ---------------------------------------------------------------------------
def _load_json(path: Path) -> Any:
    """Tolerant JSON read: a corrupt artifact degrades to an error marker instead of failing the call."""
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"error": f"corrupt or unreadable: {path.name}"}


def eddy_doctor() -> dict:
    """Hardware + provider detection and an environment preflight. No config writes; may briefly probe
    a local Ollama (<=5s). Does not contact any cloud provider."""
    from eddy.doctor import detect, preflight

    with _quiet():
        return {"detect": detect(), "preflight": preflight()}


def eddy_runs() -> dict:
    """List every run (slug, phase, best iteration), newest first."""
    from eddy.batch import list_runs

    with _quiet():
        runs = list_runs(load_config().runs_dir)
    return {"runs": list(reversed(runs)), "count": len(runs)}


def eddy_run_inspect(run: str) -> dict:
    """State + artifact inventory for one run (by slug or path)."""
    run_dir = _resolve_run(run)
    if not run_dir.exists():
        return {"error": f"no run at {run_dir}"}
    state = {}
    sj = run_dir / "state.json"
    if sj.exists():
        try:
            state = json.loads(sj.read_text())
        except json.JSONDecodeError:
            state = {}
    final = run_dir / "final"
    artifacts = sorted(p.name for p in final.iterdir()) if final.exists() else []
    return {"run_dir": str(run_dir), "slug": run_dir.name, "state": state, "final_artifacts": artifacts}


def eddy_profiles() -> dict:
    """The configured per-channel run profiles."""
    cfg = load_config()
    return {"profiles": {name: prof.model_dump() for name, prof in cfg.profiles.items()}}


def eddy_edit_options(source: str, format: str = "youtube", focus: str | None = None) -> dict:
    """Return plain-English edit-path choices and setup suggestions for this machine.

    Agents should call this before eddy_edit_start. Ask "How do you want this edited?" only when
    requires_choice=true; otherwise use selected_option_id.
    """
    from eddy.doctor import detect
    from eddy.edit_options import edit_path_options

    with _quiet():
        cfg = load_config()
        return edit_path_options(
            detect(),
            source=source,
            format=format,
            focus=focus,
            cost_cap_usd=float(getattr(cfg.loop, "max_run_cost_usd", 0.0) or 0.0),
        )


def eddy_qa(run: str, iteration: int | None = None) -> dict:
    """Run deterministic QA (+ judge if a proxy exists) on a run iteration or the final."""
    from eddy.qa.gate import qa_run

    with _quiet():
        return qa_run(_resolve_run(run), iteration=iteration)


def eddy_pick(run: str) -> dict:
    """Deterministic A/B title + thumbnail pick; returns the ab-pick decision."""
    from eddy.package.abpick import build_ab_pick

    with _quiet():
        out = build_ab_pick(_resolve_run(run))
    return {"ab_pick_path": str(out), "ab_pick": json.loads(out.read_text())}


def eddy_artifacts(run: str) -> dict:
    """Read a run's launch-kit text artifacts (titles, description, chapters, A/B summary, ledger).

    Video files are listed with sizes, never returned as bytes.
    """
    run_dir = _resolve_run(run)
    final = run_dir / "final"
    if not final.exists():
        return {"error": f"no final/ in {run_dir}"}
    out: dict[str, Any] = {"run_dir": str(run_dir)}
    titles = final / "titles.json"
    if titles.exists():
        out["titles"] = _load_json(titles)
    out["description"] = _read_text(final / "description.md")
    out["chapters"] = _read_text(final / "chapters.csv")
    out["ab_test"] = _read_text(final / "AB-TEST.md")
    ledger = final / "shorts" / "shorts-ledger.json"
    if ledger.exists():
        out["shorts_ledger"] = _load_json(ledger)
    out["videos"] = [
        {"name": p.name, "bytes": p.stat().st_size}
        for p in sorted(final.rglob("*.mp4"))
    ]
    return out


# --- jobs (subprocess) ----------------------------------------------------------------------------
def eddy_run_start(
    source: str,
    target_minutes: float | None = None,
    slug: str | None = None,
    language: str | None = None,
    format: str | None = None,
    profile: str | None = None,
    local_only: bool = False,
    edit_path: str | None = None,
    auto_fallback: bool = True,
    skip_shorts: bool | None = None,
    skip_package: bool | None = None,
) -> dict:
    """Start a full autonomous edit (transcribe -> loop -> render -> shorts -> launch kit) as a job."""
    job = jobs().start_run(
        source, slug=slug, target_minutes=target_minutes, language=language, fmt=format,
        profile=profile, local_only=local_only, edit_path=edit_path, auto_fallback=auto_fallback,
        skip_shorts=skip_shorts, skip_package=skip_package,
    )
    return {"job_id": job.id, "kind": job.kind, "run_dir": str(job.run_dir), "pid": getattr(job.proc, "pid", None)}


def eddy_edit_start(
    source: str,
    slug: str | None = None,
    focus: str | None = None,
    template: str | None = None,
    language: str | None = None,
    format: str | None = "youtube",
    edit_path: str | None = None,
    auto_fallback: bool = True,
    fallback_policy: str = "agent_subscription",
    repair: bool = False,
    dry_run: bool = False,
) -> dict:
    """Start Eddy's one-sentence edit flow as a job: finished YouTube edit, or exact blockers."""
    job = jobs().start_edit(
        source,
        slug=slug,
        focus=focus,
        template=template,
        language=language,
        fmt=format,
        edit_path=edit_path,
        auto_fallback=auto_fallback,
        fallback_policy=fallback_policy,
        repair=repair,
        dry_run=dry_run,
    )
    return {"job_id": job.id, "kind": job.kind, "run_dir": str(job.run_dir), "pid": getattr(job.proc, "pid", None)}


def eddy_host_packet(job_id: str) -> dict:
    """Return the bounded transcript/QA packet for a host-agent edit. Never returns media bytes."""
    from eddy.host_agent import host_packet

    return host_packet(_resolve_run(job_id))


def eddy_host_submit(job_id: str, payload: dict) -> dict:
    """Submit host-agent EditDecisions JSON and compile it through Eddy's deterministic compiler."""
    from eddy.host_agent import submit_host_decisions

    return submit_host_decisions(_resolve_run(job_id), payload)


def eddy_shorts_start(source: str, slug: str | None = None, language: str | None = None) -> dict:
    """Mine vertical shorts from raw footage (no full edit loop) as a job."""
    job = jobs().start_shorts(source, slug=slug, language=language)
    return {"job_id": job.id, "kind": job.kind, "run_dir": str(job.run_dir)}


def eddy_transcribe_start(source: str, slug: str | None = None, language: str | None = None) -> dict:
    """Transcribe a source (word-level + packed transcript + silence map) as a job."""
    job = jobs().start_transcribe(source, slug=slug, language=language)
    return {"job_id": job.id, "kind": job.kind, "run_dir": str(job.run_dir)}


def eddy_render_start(run: str, proxy: bool = False) -> dict:
    """Render the long edit (proxy or final) for an existing run as a job."""
    job = jobs().start_render(str(_resolve_run(run)), proxy=proxy)
    return {"job_id": job.id, "kind": job.kind, "run_dir": str(job.run_dir)}


def eddy_batch_start(path: str, skip_shorts: bool = False, skip_package: bool = False) -> dict:
    """Process many sources under a directory as a resumable queue, as a job."""
    job = jobs().start_batch(path, skip_shorts=skip_shorts, skip_package=skip_package)
    return {"job_id": job.id, "kind": job.kind}


def eddy_job_status(job_id: str) -> dict:
    """Status of a job: running / completed / failed (with log tail) / interrupted, plus run phase."""
    return jobs().status(job_id)


def eddy_job_cancel(job_id: str) -> dict:
    """Terminate a running job."""
    return jobs().cancel(job_id)


def eddy_jobs() -> dict:
    """Status of every job this server has started."""
    return {"jobs": jobs().list()}


# --- destructive (confirm-gated) ------------------------------------------------------------------
def eddy_clean(run: str, confirm: bool = False, dry_run: bool = False) -> dict:
    """Reclaim disk for a run (prune scratch / proxies / wav, keep deliverables). Needs confirm=true."""
    from eddy.clean import clean_run

    if not (confirm or dry_run):
        return {"refused": True, "reason": "clean is destructive; pass confirm=true (or dry_run=true to preview)"}
    with _quiet():
        return clean_run(_resolve_run(run), dry_run=dry_run)


def eddy_purge(run: str, full: bool = False, confirm: bool = False, dry_run: bool = False) -> dict:
    """GDPR/CCPA purge of a run's PII (full=true erases the whole run). IRREVERSIBLE — needs confirm=true."""
    from eddy.clean import purge_run

    if not (confirm or dry_run):
        return {"refused": True, "reason": "purge is irreversible; pass confirm=true (or dry_run=true to preview)"}
    with _quiet():
        return purge_run(_resolve_run(run), full=full, dry_run=dry_run)
