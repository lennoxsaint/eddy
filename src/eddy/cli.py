"""Eddy CLI — drop raw footage in, get a launch kit out."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="eddy",
    help="Local-first agentic video editor: raw footage in, YouTube launch kit out.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: bool) -> None:
    if value:
        from eddy import __version__

        typer.echo(f"eddy {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """Eddy CLI."""


@app.command()
def doctor(
    ping: bool = typer.Option(False, "--ping", help="Round-trip the active provider, incl. JSON-schema output."),
    all_providers: bool = typer.Option(False, "--all", help="Ping every configured provider."),
    write: bool = typer.Option(True, help="Write recommendations into config."),
) -> None:
    """Detect hardware + brains, recommend a provider tier, write config."""
    from eddy.doctor import run_doctor

    run_doctor(ping=ping, all_providers=all_providers, write=write)


@app.command()
def run(
    source: Path = typer.Argument(..., help="Footage dir (camera.mp4 [+ screen.mp4 + mic.wav]) or a single video file."),
    target_minutes: Optional[float] = typer.Option(None, help="Target runtime for the long edit (minutes)."),
    slug: Optional[str] = typer.Option(None, help="Run slug; defaults to date + source name."),
    resume: bool = typer.Option(False, help="Resume an interrupted run for this source."),
    skip_shorts: Optional[bool] = typer.Option(None, "--skip-shorts/--no-skip-shorts", help="Skip shorts rendering (overrides the profile)."),
    skip_package: Optional[bool] = typer.Option(None, "--skip-package/--no-skip-package", help="Skip packaging (overrides the profile)."),
    local_only: bool = typer.Option(
        False, "--local-only", help="Fully on-device: local brain only, no model downloads, no cloud thumbnail APIs."
    ),
    language: Optional[str] = typer.Option(None, "--language", help="Force transcription language (e.g. en, es); default auto-detect."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Check environment + that the footage decodes, then exit (no transcribe/render)."),
    format: Optional[str] = typer.Option(None, "--format", help="Content profile: default | tutorial | lesson | longform | podcast (raises the length ceiling)."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Named per-channel profile from config [profiles]. Explicit flags override it."),
) -> None:
    """Fully autonomous: transcribe -> edit loop -> final render -> shorts -> launch kit."""
    from eddy.config import load_config, resolve_profile
    from eddy.formats import resolve_format

    try:
        prof = resolve_profile(load_config(), profile)
    except KeyError as e:
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(1) from e
    # effective options: an explicit CLI flag wins; otherwise fall back to the profile, then defaults.
    target_minutes = target_minutes if target_minutes is not None else prof.target_minutes
    language = language if language is not None else prof.language
    skip_shorts = skip_shorts if skip_shorts is not None else bool(prof.skip_shorts)
    skip_package = skip_package if skip_package is not None else bool(prof.skip_package)
    eff_format = format if format is not None else (prof.format or "default")
    ceiling_minutes = resolve_format(eff_format)["ceiling_minutes"]
    if local_only:
        from eddy.privacy import set_offline

        set_offline(True)

    if dry_run:
        from eddy.doctor import preflight
        from eddy.runs import assert_sources_decodable, discover_sources, sha256_file

        ok = True
        for c in preflight():
            mark = "ok  " if c["ok"] else "FAIL"
            typer.echo(f"{c['check']:13} {mark} {c['detail']}")
            ok = ok and c["ok"]
        try:
            srcs = discover_sources(source)
            assert_sources_decodable({k: str(v) for k, v in srcs.items()})
            typer.echo(f"sources       ok   {', '.join(f'{k}={v.name}' for k, v in srcs.items())}")
            # touch the hash path so a permission/IO problem surfaces now, not mid-run
            sha256_file(next(iter(srcs.values())))
        except Exception as e:
            from eddy.errors import friendly_error

            head, nxt = friendly_error(e)
            typer.echo(f"sources       FAIL {head}\n              → {nxt}", err=True)
            ok = False
        typer.echo("\ndry run: " + ("OK — ready to run" if ok else "problems found (see FAIL above)"))
        raise typer.Exit(0 if ok else 1)

    from eddy.loop.controller import autonomous_run

    try:
        autonomous_run(
            source=source,
            target_minutes=target_minutes,
            slug=slug,
            resume=resume,
            skip_shorts=skip_shorts,
            skip_package=skip_package,
            language=language,
            ceiling_minutes=ceiling_minutes,
        )
    except Exception as e:
        from eddy.beacon import send_failure_beacon
        from eddy.errors import friendly_error, write_crash_log

        headline, next_step = friendly_error(e)
        log = write_crash_log(e)
        send_failure_beacon(e, stage="run")  # opt-in + anonymized; no-op by default
        typer.echo(f"\n✗ {headline}\n  → {next_step}\n  crash log: {log}", err=True)
        raise typer.Exit(1) from e


@app.command()
def batch(
    path: Path = typer.Argument(..., help="A footage root (each subdir/video = one source) or a single source."),
    skip_shorts: bool = typer.Option(False, help="Skip shorts rendering for every item."),
    skip_package: bool = typer.Option(False, help="Skip packaging for every item."),
    json_out: bool = typer.Option(False, "--json", help="Emit the summary as JSON (headless)."),
) -> None:
    """Process MANY sources as a resumable queue, continuing past per-item failures."""
    from eddy.batch import discover_batch_sources, run_batch

    sources = discover_batch_sources(path)
    if not sources:
        typer.echo(f"no sources found under {path}", err=True)
        raise typer.Exit(1)
    summary = run_batch(sources, skip_shorts=skip_shorts, skip_package=skip_package)
    if json_out:
        import json as _json

        typer.echo(_json.dumps(summary, indent=1))
    else:
        typer.echo(f"batch: {summary['succeeded']}/{summary['total']} ok, {summary['failed']} failed")
        for i in summary["items"]:
            mark = "ok  " if i["status"] == "ok" else "FAIL"
            typer.echo(f"  {mark} {i['source']}" + (f" — {i.get('error','')}" if i["status"] == "failed" else ""))
    raise typer.Exit(1 if summary["failed"] else 0)


@app.command()
def runs() -> None:
    """List all runs (fleet view): slug, phase, best iteration."""
    from eddy.batch import list_runs
    from eddy.config import load_config

    rows = list_runs(load_config().runs_dir)
    if not rows:
        typer.echo("no runs yet")
        return
    for r in rows:
        typer.echo(f"  {r['slug']:40} {r['phase']:24} best={r['best_iter']}")


@app.command()
def profiles() -> None:
    """List configured per-channel run profiles (config [profiles])."""
    from eddy.config import load_config

    cfg = load_config()
    if not cfg.profiles:
        typer.echo("no profiles configured — add a [profiles.<name>] table to your eddy config")
        return
    for name, p in sorted(cfg.profiles.items()):
        overrides = {k: v for k, v in p.model_dump().items() if v is not None}
        typer.echo(f"  {name:20} {overrides or '(no overrides)'}")


@app.command()
def transcribe(
    source: Path = typer.Argument(...),
    slug: Optional[str] = typer.Option(None),
    language: Optional[str] = typer.Option(None, "--language", help="Force language (e.g. en, es); default auto-detect."),
) -> None:
    """Stage: word-level transcription + packed transcript + silence map."""
    from eddy.runs import open_run
    from eddy.transcribe.whisper import transcribe_run

    run_dir = open_run(source, slug=slug)
    transcribe_run(run_dir, language=language)


@app.command()
def plan(run_dir: Path = typer.Argument(..., help="Run directory (runs/<date-slug>)")) -> None:
    """Stage: editorial cut plan -> edit-decisions.json + edl.json + sim report."""
    from eddy.edit.cutplan import plan_run

    plan_run(run_dir)


@app.command()
def pick(run_dir: Path = typer.Argument(..., help="Run directory (runs/<date-slug>)")) -> None:
    """A/B pick: score the title candidates (deterministic rubric) + pair thumbnails -> AB-TEST.md."""
    from eddy.package.abpick import build_ab_pick

    out = build_ab_pick(run_dir)
    import json as _json

    res = _json.loads(out.read_text())
    a, b = res["title"]["a"], res["title"]["b"]
    if a:
        typer.echo(f"A (score {a['score']}): {a['title']}")
    if b:
        typer.echo(f"B (score {b['score']}): {b['title']}")
    if not a:
        typer.echo("no title candidates found — run packaging first")
    typer.echo(f"→ {out.parent / 'AB-TEST.md'}")


@app.command()
def render(
    run_dir: Path = typer.Argument(...),
    proxy: bool = typer.Option(False, "--proxy", help="480p proxy instead of final."),
    iteration: Optional[int] = typer.Option(None, help="Render a specific iteration's EDL."),
) -> None:
    """Stage: render the long edit (proxy or final) from the current EDL."""
    from eddy.render.long import render_run

    render_run(run_dir, proxy=proxy, iteration=iteration)


@app.command()
def shorts(
    source: Path = typer.Argument(..., help="An existing run dir (render stage) OR raw footage (standalone mine)."),
    slug: Optional[str] = typer.Option(None),
    resume: bool = typer.Option(False, "--resume", help="Resume an existing run dir for this source."),
    language: Optional[str] = typer.Option(None, "--language", help="Force language (e.g. en, es); default auto-detect."),
) -> None:
    """Render karaoke-caption shorts. Pass an existing run dir to render from its decisions, or raw
    footage to mine clips standalone (transcribe -> one decision pass -> shorts; no long edit loop)."""
    source = source.expanduser()
    if source.is_dir() and (source / "manifest.json").exists() and (source / "iterations").exists():
        from eddy.render.shorts import render_shorts  # stage mode: existing run dir

        render_shorts(source)
        return

    from eddy.errors import friendly_error, write_crash_log
    from eddy.loop.controller import mine_shorts  # standalone mode: raw footage

    try:
        mine_shorts(source=source, slug=slug, resume=resume, language=language)
    except Exception as e:
        headline, next_step = friendly_error(e)
        log = write_crash_log(e)
        typer.echo(f"\n✗ {headline}\n  → {next_step}\n  crash log: {log}", err=True)
        raise typer.Exit(1) from e


@app.command()
def package(run_dir: Path = typer.Argument(...)) -> None:
    """Stage: titles, chapters, description, thumbnails, launch kit."""
    from eddy.package.launch_kit import package_run

    package_run(run_dir)


@app.command()
def qa(
    run_dir: Path = typer.Argument(...),
    iteration: Optional[int] = typer.Option(None),
) -> None:
    """Stage: run deterministic QA (+judge if a proxy exists) on an iteration."""
    from eddy.qa.gate import qa_run

    qa_run(run_dir, iteration=iteration)


@app.command()
def status(run_dir: Path = typer.Argument(...)) -> None:
    """Show run state: iteration, gates, judge scores, artifacts."""
    from eddy.clean import dir_size_bytes
    from eddy.loop.state import print_status

    print_status(run_dir)
    typer.echo(f"disk_usage_mb: {round(dir_size_bytes(run_dir) / 2**20, 1)}")


@app.command()
def bundle(
    run_dir: Path = typer.Argument(..., help="Run directory to bundle for a bug report."),
    out: Optional[Path] = typer.Option(None, "-o", "--out", help="Output zip path (default: <run>/eddy-bundle.zip)."),
) -> None:
    """Create a redacted diagnostic archive (audit trail + env, PII stripped) for a bug report."""
    from eddy.bundle import build_bundle

    path = build_bundle(run_dir, out)
    typer.echo(f"diagnostic bundle: {path}")
    typer.echo("(redacted: transcript text + home paths stripped; no footage/transcript/faces included)")


@app.command()
def clean(
    run_dir: Path = typer.Argument(..., help="Run directory to prune scratch from."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be freed without deleting."),
) -> None:
    """Reclaim disk: prune segment scratch / proxy renders / the 16k WAV, keeping deliverables."""
    from eddy.clean import clean_run

    info = clean_run(run_dir, dry_run=dry_run)
    verb = "would free" if dry_run else "freed"
    typer.echo(f"{verb} {info['freed_mb']}MB across {len(info['removed'])} item(s)")
    for r in info["removed"]:
        typer.echo(f"  {r}")


@app.command()
def purge(
    run_dir: Path = typer.Argument(..., help="Run directory to purge personal data from."),
    full: bool = typer.Option(False, "--full", help="Delete the ENTIRE run directory (complete erasure)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be purged without deleting."),
) -> None:
    """GDPR/CCPA: delete PII (transcript, face frames, caption text). --full erases the whole run."""
    from eddy.clean import purge_run

    info = purge_run(run_dir, full=full, dry_run=dry_run)
    verb = "would purge" if dry_run else "purged"
    typer.echo(f"{verb} {info['freed_mb']}MB of personal data ({len(info['removed'])} item(s))")
    for r in info["removed"]:
        typer.echo(f"  {r}")


if __name__ == "__main__":
    app()
