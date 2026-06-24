"""Eddy CLI — drop raw footage in, get a launch kit out."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="eddy",
    help="Local-first agentic video editor: raw footage in, YouTube launch kit out.",
    no_args_is_help=False,  # bare `eddy` wakes the mascot instead of dumping help (`eddy --help` still helps)
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: bool) -> None:
    if value:
        from eddy import __version__

        typer.echo(f"eddy {__version__}")
        raise typer.Exit()


def _recent_runs() -> list[dict] | None:
    """Best-effort newest-first run list for the wake screen. Never raises — the splash must be instant."""
    try:
        from eddy.batch import list_runs
        from eddy.config import load_config

        cfg = load_config()
        runs = list_runs(Path(str(cfg.paths.runs_dir)).expanduser())
        return list(reversed(runs))[:2] if runs else None
    except Exception:
        return None


def _wake(no_tui: bool) -> None:
    """Bare `eddy`: open the full-screen TUI on an interactive terminal, else print the banner.

    Piped / non-TTY / `--no-tui` (and CI, and the MCP subprocess) get the banner, so only an
    interactive human ever drops into the app. A missing Textual degrades to the banner too.
    """
    import sys

    interactive = bool(getattr(sys.stdout, "isatty", lambda: False)()) and bool(getattr(sys.stdin, "isatty", lambda: False)())
    if interactive and not no_tui:
        try:
            from eddy.tui.app import run_tui
        except ImportError:
            run_tui = None  # type: ignore[assignment]
        if run_tui is not None:
            run_tui()
            return
    from eddy.ui import console as ui

    ui.console().print(ui.wake_screen(runs=_recent_runs()))


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
    no_tui: bool = typer.Option(False, "--no-tui", help="Print the banner instead of opening the full-screen TUI."),
) -> None:
    """Eddy CLI."""
    from eddy.ui.console import harden_stdout

    harden_stdout()  # UTF-8 every invocation, before any glyph hits a legacy console
    # Bare `eddy` (no subcommand) wakes Eddy: the TUI on a terminal, else the branded splash.
    if ctx.invoked_subcommand is None:
        _wake(no_tui)
        raise typer.Exit()


@app.command()
def tui() -> None:
    """Open the full-screen Eddy TUI (runs list, live monitor, command/NL input)."""
    from eddy.tui.app import run_tui

    run_tui()


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
def bootstrap(
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show the exact repair plan needed before Eddy can edit reliably."""
    import json

    from eddy.bootstrap import repair_plan
    from eddy.doctor import preflight

    checks = preflight()
    plan = repair_plan(checks)
    out = {"preflight": checks, "repair_plan": plan}
    if json_out:
        typer.echo(json.dumps(out, indent=2))
        raise typer.Exit(0 if plan["status"] == "ready" else 1)
    for check in checks:
        mark = "ok  " if check["ok"] else "FAIL"
        typer.echo(f"{check['check']:13} {mark} {check['detail']}")
    if plan["status"] == "ready":
        typer.echo("\nbootstrap: ready")
        return
    typer.echo("\nbootstrap: repair needed")
    for action in plan["actions"]:
        typer.echo(f"  - {action['id']}: {action['title']}")
        if action.get("command"):
            typer.echo(f"    command: {action['command']}")
        typer.echo(f"    why: {action['reason']}")
    raise typer.Exit(1)


@app.command("update-check")
def update_check(
    remote: str = typer.Option("origin", "--remote", help="Git remote to compare against."),
    branch: str = typer.Option("main", "--branch", help="Remote branch to compare against."),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Check whether this Eddy checkout has updates. Notify-only; never pulls."""
    import json

    from eddy.update_check import check_for_update

    result = check_for_update(remote=remote, branch=branch)
    if json_out:
        typer.echo(json.dumps(result, indent=2))
        return
    status = result.get("status", "unknown")
    if result.get("ok") and status == "update_available":
        typer.echo(f"update available: {result['local_sha'][:8]} -> {result['remote_sha'][:8]}")
        typer.echo(result["next_action"])
    elif result.get("ok"):
        typer.echo(f"up to date: {result.get('local_sha', '')[:8]}")
    else:
        typer.echo(f"update check failed: {status} ({result.get('error', 'no detail')})", err=True)
        raise typer.Exit(1)


@app.command()
def mascot(
    state: Optional[str] = typer.Option(None, "--state", help="idle | thinking | working | success | error."),
    small: bool = typer.Option(False, "--small", help="Show the compact eagle instead of the hero size."),
    animate: bool = typer.Option(False, "--animate", help="Run a short animation demo (interactive terminals)."),
) -> None:
    """Preview Eddy the eagle: the wake screen, a single sprite state, or a short animation demo."""
    from eddy.ui import console as ui

    if animate:
        import time

        from eddy.ui.animate import animate as run_anim

        with run_anim(status="[eddy.accent]editing…[/eddy.accent] cut 3/6 · q0.82", state="working", final_state="success") as h:
            time.sleep(1.8)
            h.update(status="[eddy.accent]rendering final…[/eddy.accent]")
            time.sleep(1.4)
        ui.ok("done · launch kit ready")
        return
    if state:
        ui.print_sprite(state, small=small)
        return
    ui.console().print(ui.wake_screen(runs=_recent_runs()))


mcp_app = typer.Typer(name="mcp", help="Eddy MCP server: serve it over stdio, or install it into a client.", no_args_is_help=True)
app.add_typer(mcp_app)

studio_sound_app = typer.Typer(
    name="studio-sound",
    help="Install or inspect Eddy's heavy local Studio Sound backend.",
    no_args_is_help=True,
)
app.add_typer(studio_sound_app)

motion_app = typer.Typer(
    name="motion",
    help="HyperFrames-backed motion contracts: pin/cache registry assets and create frame/storyboard proofs.",
    no_args_is_help=True,
)
app.add_typer(motion_app)

hooks_app = typer.Typer(
    name="hooks",
    help="Build and validate Eddy's offline short-form hook playbook.",
    no_args_is_help=True,
)
app.add_typer(hooks_app)

DEFAULT_HYPERFRAMES_ROOT = Path.home() / "Developer" / "hyperframes"


@studio_sound_app.command("doctor")
def studio_sound_doctor(json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON.")) -> None:
    """Check whether the local Studio Sound quality backend is installed."""
    import json

    from eddy.studio_sound_env import status

    res = status()
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    mark = "OK " if res["quality_ready"] else "FAIL"
    typer.echo(f"studio sound {mark} {res.get('deep_filter') or 'missing DeepFilterNet backend'}")
    if not res["quality_ready"]:
        typer.echo("next: eddy studio-sound install")


@studio_sound_app.command("install")
def studio_sound_install(
    force: bool = typer.Option(False, "--force", help="Recreate the Studio Sound env before installing."),
    include_resemble: bool = typer.Option(False, "--include-resemble", help="Also try the optional Resemble Enhance backend."),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Provision Eddy's default heavy local Studio Sound backend."""
    import json

    from eddy.studio_sound_env import install_studio_sound

    res = install_studio_sound(force=force, include_resemble=include_resemble)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
    elif res.get("ok"):
        typer.echo(f"studio sound OK — {res['status'].get('deep_filter')}")
    else:
        typer.echo(f"studio sound FAIL at {res.get('stage')}: {res.get('error')}", err=True)
        typer.echo(f"next: {res.get('next_action', 'fix the dependency error and rerun')}", err=True)
    if not res.get("ok"):
        raise typer.Exit(1)


@motion_app.command("update-hyperframes")
def motion_update_hyperframes(
    hyperframes_root: Path = typer.Option(
        DEFAULT_HYPERFRAMES_ROOT,
        "--hyperframes-root",
        help="Local HyperFrames checkout to pin and index.",
    ),
    cache_dir: Path = typer.Option(Path(".eddy/hyperframes-cache"), "--cache-dir", help="Where to write the pin/index."),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Pin/index the local HyperFrames checkout. Notify-only; never git-pulls."""
    import json

    from eddy.motion.frame_spec import write_hyperframes_cache

    if not hyperframes_root.exists():
        typer.echo(f"HyperFrames checkout not found: {hyperframes_root}", err=True)
        raise typer.Exit(1)
    res = write_hyperframes_cache(hyperframes_root, cache_dir)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    typer.echo(f"indexed {res['asset_count']} HyperFrames assets at {res['commit'][:12]} -> {cache_dir}")


@motion_app.command("init-contract")
def motion_init_contract(
    project_dir: Path = typer.Argument(..., help="Content/project folder that needs motion artifacts."),
    hyperframes_root: Path = typer.Option(
        DEFAULT_HYPERFRAMES_ROOT,
        "--hyperframes-root",
        help="Local HyperFrames checkout to copy selected references from.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Create frame.md, storyboard.md/html, and a copied HyperFrames asset manifest for a run."""
    import json

    from eddy.motion.frame_spec import build_threadify_motion_contract

    if not hyperframes_root.exists():
        typer.echo(f"HyperFrames checkout not found: {hyperframes_root}", err=True)
        raise typer.Exit(1)
    res = build_threadify_motion_contract(project_dir, hyperframes_root)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    typer.echo(f"frame: {res['frame_spec']}")
    typer.echo(f"storyboard: {res['storyboard']}")
    typer.echo(f"storyboard html: {res['storyboard_html']}")
    typer.echo(f"copied manifest: {res['copied_assets_manifest']}")


@hooks_app.command("status")
def hooks_status(
    playbook: Path = typer.Option(Path("docs/references/short-form-hook-playbook.jsonl"), "--playbook"),
    min_records: int = typer.Option(1000, "--min-records"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Validate the baked offline short-form hook playbook."""
    import json

    from eddy.hooks.playbook import playbook_status

    res = playbook_status(playbook, min_records=min_records)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    if res["ready"]:
        typer.echo(f"hook playbook ready: {res['valid_count']}/{res['required_count']} valid hooks")
    else:
        typer.echo(f"{res['blocker']}: {res['valid_count']}/{res['required_count']} valid hooks at {playbook}", err=True)
        raise typer.Exit(1)


@hooks_app.command("build-supadata")
def hooks_build_supadata(
    urls_file: Path = typer.Argument(..., help="Text file with one public short-form URL per line."),
    out: Path = typer.Option(Path("docs/references/short-form-hook-playbook.jsonl"), "--out"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Build the hook corpus once from supplied public URLs via Supadata."""
    import json

    from eddy.hooks.playbook import build_from_supadata

    urls = [line.strip() for line in urls_file.read_text().splitlines() if line.strip() and not line.startswith("#")]
    res = build_from_supadata(urls, out)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    typer.echo(f"wrote {res['valid_count']} valid hooks -> {out}")
    if not res["ready"]:
        typer.echo(f"{res['blocker']}: collect more proven public URLs and rerun", err=True)
        raise typer.Exit(1)


@hooks_app.command("build-youtube-metadata")
def hooks_build_youtube_metadata(
    out: Path = typer.Option(Path("docs/references/short-form-hook-playbook.jsonl"), "--out"),
    queries_file: Optional[Path] = typer.Option(None, "--queries-file", help="Optional newline-delimited ytsearch queries."),
    target_records: int = typer.Option(1000, "--target-records"),
    per_query: int = typer.Option(80, "--per-query"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Build the offline corpus from public YouTube metadata without downloading media/transcripts."""
    import json

    from eddy.hooks.playbook import build_from_youtube_metadata

    queries = None
    if queries_file:
        queries = [line.strip() for line in queries_file.read_text().splitlines() if line.strip() and not line.startswith("#")]
    res = build_from_youtube_metadata(out, queries=queries, target_records=target_records, per_query=per_query)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    typer.echo(f"wrote {res['valid_count']} valid metadata hooks -> {out}")
    if not res["ready"]:
        typer.echo(f"{res['blocker']}: add more public queries or use Supadata URLs", err=True)
        raise typer.Exit(1)


@mcp_app.command("serve")
def mcp_serve() -> None:
    """Run the Eddy MCP server over stdio (what a client launches; not for interactive use)."""
    from eddy.mcp_server.server import main

    main()


@mcp_app.command("install")
def mcp_install(
    client: str = typer.Option(..., "--client", help="claude-desktop | claude-code | codex."),
    command: str = typer.Option("eddy-mcp", "--command", help="The server command the client should launch."),
    path: Optional[Path] = typer.Option(None, "--path", help="Override the client's config path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be written, change nothing."),
) -> None:
    """Register the Eddy MCP server with a client (idempotent; backs up + merges, never clobbers)."""
    from eddy.mcp_server.install import CLIENTS, install

    if client not in CLIENTS:
        typer.echo(f"✗ unknown client {client!r}; choose one of {', '.join(CLIENTS)}", err=True)
        raise typer.Exit(1)
    res = install(client, command=command, path=path, dry_run=dry_run)
    from eddy.ui import console as ui

    if dry_run:
        ui.note(f"would write {res['path']}:")
        ui.console().print(res["content"])
        return
    ui.ok(f"{res['action']} {res['path']} — mcpServers.eddy → {command}")
    if res.get("backup"):
        ui.note(f"backup: {res['backup']}")


@app.command()
def edit(
    source: Path = typer.Argument(..., help="Raw footage folder or single video file."),
    slug: Optional[str] = typer.Option(None, help="Run slug; defaults to date + source name."),
    focus: Optional[str] = typer.Option(None, "--focus", help="One-sentence brief for what to make."),
    template: Optional[str] = typer.Option(None, "--template", help="Force an Eddy template id."),
    language: str = typer.Option("en", "--language", help="Transcription language."),
    format: str = typer.Option("youtube", "--format", help="Content format profile."),
    repair: bool = typer.Option(False, "--repair", help="Record repair intent and include repair actions in blockers."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Prepare and validate only; do not transcribe/render."),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """One-sentence flow: footage in, finished edit out, or an exact blocker + support bundle."""
    import json

    from eddy.one_sentence import edit as run_edit

    try:
        result = run_edit(
            source,
            slug=slug,
            focus=focus,
            template_id=template,
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
            focus=focus,
            focus_mode=focus_mode,
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
