"""Core pipeline commands: edit, run, batch, runs, profiles, transcribe, plan,
pick, render, shorts, package, qa, status, bundle, clean, purge."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from eddy.cli._app import app


@app.command()
def edit(
    source: Path = typer.Argument(..., help="Raw footage folder or single video file."),
    slug: Optional[str] = typer.Option(None, help="Run slug; defaults to date + source name."),
    focus: Optional[str] = typer.Option(None, "--focus", help="One-sentence brief for what to make."),
    template: Optional[str] = typer.Option(None, "--template", help="Force an Eddy template id."),
    language: str = typer.Option("en", "--language", help="Transcription language."),
    format: str = typer.Option("youtube", "--format", help="Content format profile."),
    edit_path: Optional[str] = typer.Option(
        None,
        "--edit-path",
        help="Editing route to use: host_agent, codex_cli, claude_cli, local, openai_api, or anthropic_api.",
    ),
    auto_fallback: bool = typer.Option(
        True,
        "--auto-fallback/--no-auto-fallback",
        help="Automatically fall back to the best available proof-gated route when the selected route stalls or fails.",
    ),
    fallback_policy: str = typer.Option(
        "agent_subscription",
        "--fallback-policy",
        help="Fallback policy. Default prefers the current host agent/subscription path.",
    ),
    repair: bool = typer.Option(False, "--repair", help="Record repair intent and include repair actions in blockers."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Prepare and validate only; do not transcribe/render."),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """One-sentence flow: footage in, proof-gated edit out, or an exact blocker + support bundle."""
    import json

    from eddy.one_sentence import edit as run_edit

    try:
        result = run_edit(
            source,
            slug=slug,
            focus=focus,
            template_id=template,
            edit_path=edit_path,
            auto_fallback=auto_fallback,
            fallback_policy=fallback_policy,
            format_name=format,
            language=language,
            repair=repair,
            dry_run=dry_run,
        )
    except Exception as e:
        from eddy.errors import friendly_error, write_crash_log

        headline, next_step = friendly_error(e)
        log = write_crash_log(e)
        typer.echo(f"\n✗ {headline}\n  → {next_step}\n  crash log: {log}", err=True)
        raise typer.Exit(1) from e
    if json_out:
        typer.echo(json.dumps(result, indent=2))
        raise typer.Exit(0 if result["status"] in {"ready", "completed"} else 1)
    if result["status"] == "completed":
        typer.echo(f"✓ edit complete: {result['run_dir']}")
        typer.echo(f"  long form: {result['outputs']['long_form']}")
        typer.echo(f"  shorts:    {result['outputs']['shorts_dir']}")
        return
    if result["status"] == "ready":
        typer.echo(f"✓ ready: {result['run_dir']}")
        typer.echo("  next: run the same command without --dry-run")
        return
    typer.echo(f"✗ blocked: {result['run_dir']}", err=True)
    for blocker in result["blockers"]:
        typer.echo(f"  - {blocker['code']}: {blocker['message']}", err=True)
        typer.echo(f"    fix: {blocker['fix']}", err=True)
    if result.get("support_bundle"):
        typer.echo(f"  support bundle: {result['support_bundle']}", err=True)
    raise typer.Exit(1)


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
    focus: Optional[str] = typer.Option(None, "--focus", help="Focus brief: what to keep / center the edit on (free text)."),
    extract: Optional[bool] = typer.Option(None, "--extract/--no-extract", help="Force topical EXTRACT mode (keep ONLY the focus) on/off; default auto-detects from the brief."),
    edit_path: Optional[str] = typer.Option(
        None,
        "--edit-path",
        help="Editing route to use: codex_cli, claude_cli, local, openai_api, or anthropic_api. Host-agent mode uses `eddy edit`/MCP.",
    ),
    auto_fallback: bool = typer.Option(
        True,
        "--auto-fallback/--no-auto-fallback",
        help="Record/allow automatic route fallback when a selected provider fails.",
    ),
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
    user_set_target = target_minutes is not None  # captured before the profile fallback overwrites it
    target_minutes = target_minutes if target_minutes is not None else prof.target_minutes
    language = language if language is not None else prof.language
    # focus brief: CLI flag > profile default. Mode: --extract/--no-extract wins; else auto-detect
    # from phrasing ("only keep X" -> extract, softer wording -> steer).
    focus = focus if focus is not None else prof.focus
    focus_mode: Optional[str] = None
    if focus:
        from eddy.tui.intents import is_extract_brief

        if extract is True:
            focus_mode = "extract"
        elif extract is False:
            focus_mode = "steer"
        else:
            focus_mode = "extract" if is_extract_brief(focus) else "steer"
        # an extract is a tight topical cut: shorts + the launch-kit package are meaningless on it,
        # so default those OFF unless the user explicitly asked for them.
        if focus_mode == "extract":
            if skip_shorts is None:
                skip_shorts = True
            if skip_package is None:
                skip_package = True
    skip_shorts = skip_shorts if skip_shorts is not None else bool(prof.skip_shorts)
    skip_package = skip_package if skip_package is not None else bool(prof.skip_package)
    eff_format = format if format is not None else (prof.format or "default")
    ceiling_minutes = resolve_format(eff_format)["ceiling_minutes"]
    # A runtime stated in the focus brief ("a 5-10 minute explanation") is the user's intent for how
    # long the cut should run — honor it as the loop target + length ceiling so an extract lands at the
    # requested length instead of the 12-min default. Only when no explicit --target-minutes and the
    # default format (a named format deliberately raises/disables the ceiling, so never override that).
    if focus and not user_set_target and eff_format == "default":
        from eddy.tui.intents import duration_from_brief

        band = duration_from_brief(focus)
        if band:
            target_minutes, ceiling_minutes = band
            typer.echo(
                f"[eddy] focus brief sets length → target {target_minutes:g} min, "
                f"ceiling {ceiling_minutes:g} min"
            )
    if local_only:
        from eddy.privacy import set_offline

        set_offline(True)
    from eddy.edit_options import normalize_edit_path

    selected_edit_path = normalize_edit_path(edit_path)
    if selected_edit_path == "host_agent":
        typer.echo("✗ host-agent edit path uses `eddy edit` plus eddy_host_packet/eddy_host_submit, not `eddy run`.", err=True)
        raise typer.Exit(1)
    # enforce the offline promise at the syscall boundary (covers --local-only AND EDDY_OFFLINE=1)
    from eddy.netguard import maybe_install_egress_guard

    if maybe_install_egress_guard():
        typer.echo("[eddy] --local-only: egress guard active — outbound connections are blocked.")

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
        if focus:
            typer.echo(f"focus         ok   [{focus_mode}] {focus[:70]}")
        typer.echo("\ndry run: " + ("OK — ready to run" if ok else "problems found (see FAIL above)"))
        raise typer.Exit(0 if ok else 1)

    import os

    from eddy.edit_options import provider_for_edit_path
    from eddy.loop.controller import autonomous_run

    try:
        provider = provider_for_edit_path(selected_edit_path)
        previous = os.environ.get("EDDY_EDITORIAL")
        try:
            if provider:
                os.environ["EDDY_EDITORIAL"] = provider
            autonomous_run(
                source=source,
                target_minutes=target_minutes,
                slug=slug,
                resume=resume,
                skip_shorts=skip_shorts,
                skip_package=skip_package,
                language=language,
                ceiling_minutes=ceiling_minutes,
                focus=focus,
                focus_mode=focus_mode,
            )
        finally:
            if provider:
                if previous is None:
                    os.environ.pop("EDDY_EDITORIAL", None)
                else:
                    os.environ["EDDY_EDITORIAL"] = previous
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
