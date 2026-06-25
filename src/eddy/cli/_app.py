"""Eddy CLI root app + wake helpers."""

from __future__ import annotations

from pathlib import Path

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
    except Exception as exc:
        from eddy import log

        log.debug("wake-screen run list unavailable: %s", exc)
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
