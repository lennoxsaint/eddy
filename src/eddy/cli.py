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
    skip_shorts: bool = typer.Option(False, help="Skip shorts rendering."),
    skip_package: bool = typer.Option(False, help="Skip packaging (titles/thumbnails/description)."),
    local_only: bool = typer.Option(
        False, "--local-only", help="Fully on-device: local brain only, no model downloads, no cloud thumbnail APIs."
    ),
    language: Optional[str] = typer.Option(None, "--language", help="Force transcription language (e.g. en, es); default auto-detect."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Check environment + that the footage decodes, then exit (no transcribe/render)."),
) -> None:
    """Fully autonomous: transcribe -> edit loop -> final render -> shorts -> launch kit."""
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
        )
    except Exception as e:
        from eddy.errors import friendly_error, write_crash_log

        headline, next_step = friendly_error(e)
        log = write_crash_log(e)
        typer.echo(f"\n✗ {headline}\n  → {next_step}\n  crash log: {log}", err=True)
        raise typer.Exit(1) from e


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
def render(
    run_dir: Path = typer.Argument(...),
    proxy: bool = typer.Option(False, "--proxy", help="480p proxy instead of final."),
    iteration: Optional[int] = typer.Option(None, help="Render a specific iteration's EDL."),
) -> None:
    """Stage: render the long edit (proxy or final) from the current EDL."""
    from eddy.render.long import render_run

    render_run(run_dir, proxy=proxy, iteration=iteration)


@app.command()
def shorts(run_dir: Path = typer.Argument(...)) -> None:
    """Stage: render karaoke-caption shorts from the run's decisions."""
    from eddy.render.shorts import render_shorts

    render_shorts(run_dir)


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
    from eddy.loop.state import print_status

    print_status(run_dir)


if __name__ == "__main__":
    app()
