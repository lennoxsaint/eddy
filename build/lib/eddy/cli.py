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
) -> None:
    """Fully autonomous: transcribe -> edit loop -> final render -> shorts -> launch kit."""
    from eddy.loop.controller import autonomous_run

    autonomous_run(
        source=source,
        target_minutes=target_minutes,
        slug=slug,
        resume=resume,
        skip_shorts=skip_shorts,
        skip_package=skip_package,
    )


@app.command()
def transcribe(
    source: Path = typer.Argument(...),
    slug: Optional[str] = typer.Option(None),
) -> None:
    """Stage: word-level transcription + packed transcript + silence map."""
    from eddy.runs import open_run
    from eddy.transcribe.whisper import transcribe_run

    run_dir = open_run(source, slug=slug)
    transcribe_run(run_dir)


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
