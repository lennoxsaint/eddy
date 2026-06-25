"""The one Rich console + the brand surfaces every human-facing command shares.

Everything visual funnels through here so the rest of the codebase stays dumb about styling and the
look is consistent. This module owns three things:

1. **The theme** — base brand styles plus the three accent colours the one-line `MINI` mark uses.
2. **Gating** — colour follows the terminal / ``NO_COLOR``; animation additionally requires an
   interactive TTY and no ``EDDY_NO_ANIM``. The MCP subprocess path is non-interactive, so it
   automatically gets clean, parseable, un-animated lines.
3. **Surfaces** — `wake_screen()`, `banner()`, `panel()`, `ok/warn/err/note()`, `progress()`, and
   `print_sprite()`. The eagle is drawn from `eddy.ui.pixels` half-blocks; the wordmark from
   `eddy.ui.wordmark`.

No network, no disk, no editorial state. `wake_screen(runs=...)` takes the fleet list as a parameter
so this package never imports config/batch (keeps it pure and import-cheap).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import PurePath

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeRemainingColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from eddy.ui import pixels, sprite, wordmark

_THEME = Theme(
    {
        "eddy.brand": "bold gold1",
        "eddy.accent": "gold1",
        "eddy.dim": "grey58",
        "eddy.ok": "bold green",
        "eddy.warn": "bold yellow",
        "eddy.err": "bold red",
        # accents for the one-line MINI eagle mark
        "eddy.crown": "grey93",
        "eddy.eye": "gold1",
        "eddy.beak": "orange1",
    }
)

_console: Console | None = None


def harden_stdout() -> None:
    """Make stdout/stderr UTF-8 so Eddy never crashes on its own output.

    Eddy draws ✓/✗/⚠/▸/→ and the eagle's box glyphs. On a legacy Windows console (cp1252) — or any
    stream whose encoding can't map those — a plain ``print`` or Rich write raises
    ``UnicodeEncodeError`` mid-run. Reconfigure both streams to UTF-8, replacing the rare unmappable
    glyph rather than dying. Idempotent and a no-op where already UTF-8 or where the stream can't be
    reconfigured (e.g. a captured buffer in tests). This also covers plain ``print`` paths (e.g. the
    shorts ledger / abpick) that never touch the Rich console, so it's the one global safety net."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "").replace("_", "")
        if enc == "utf8":
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass  # detached/non-text stream — leave it; callers degrade, they don't crash here


def _json_default(default: Callable[[object], object] | None = None) -> Callable[[object], object]:
    """Stable JSON fallback for receipts.

    Python stringifies ``Path`` objects with platform-native separators, so a Windows CI run turns
    ``Path("/tmp/x")`` into ``\\tmp\\x``. Eddy receipts are meant to be diffable and portable, so
    path-like objects are normalized to POSIX form before any caller-provided fallback runs.
    """

    def convert(value: object) -> object:
        if isinstance(value, PurePath):
            return value.as_posix()
        if default is not None:
            return default(value)
        raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

    return convert


def json_output(data: object, *, indent: int = 1, default: Callable[[object], object] | None = None) -> None:
    """Emit a machine-readable JSON ledger to stdout (qa gate, shorts ledger, studio-sound status).

    Deliberately bypasses the Rich console — no theme, no soft-wrap, no styling — so the line stays
    byte-for-byte parseable by whatever consumes it. But it first runs ``harden_stdout()`` so the
    UTF-8 safety net is in place even when the command never touched a human-facing surface, matching
    the guarantee ``console()`` gives the styled paths."""
    import json

    harden_stdout()
    print(json.dumps(data, indent=indent, default=_json_default(default)))


def console() -> Console:
    """The shared Rich console. Colour is left to Rich's own detection (terminal + ``NO_COLOR``), so
    piping to a file or the MCP subprocess yields plain text automatically."""
    global _console
    if _console is None:
        harden_stdout()  # before the first write, so glyphs never hit a cp1252 console
        _console = Console(theme=_THEME, highlight=False)
    return _console


def reset() -> None:
    """Drop the cached console (used by tests that toggle terminal/colour state)."""
    global _console
    _console = None


# --- gating ---------------------------------------------------------------------------------------
def color_enabled() -> bool:
    """True when the console will actually emit colour (interactive terminal, ``NO_COLOR`` unset)."""
    return bool(console().is_terminal) and not os.environ.get("NO_COLOR")


def anim_enabled() -> bool:
    """Animation is opt-out and strictly gated: real interactive TTY, colour on, ``EDDY_NO_ANIM`` unset.

    This keeps multi-frame loops off pipes, CI logs, dumb terminals, and the MCP subprocess.
    """
    if os.environ.get("EDDY_NO_ANIM"):
        return False
    try:
        if not sys.stdout.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    return color_enabled()


# --- sprite ---------------------------------------------------------------------------------------
def sprite_renderable(state: str = "idle", index: int = 0, small: bool = False) -> Text:
    """A Rich `Text` of one eagle frame.

    Half-block pixel art when colour is on; a plain-ASCII eagle when it isn't (piped / ``NO_COLOR`` /
    dumb terminal), since half-blocks are unreadable without colour.
    """
    if not color_enabled():
        return Text(sprite.ascii_art(), style="eddy.dim")
    return pixels.to_text(sprite.frame(state, index, small=small))


def print_sprite(state: str = "idle", index: int = 0, small: bool = False) -> None:
    console().print(sprite_renderable(state, index, small=small))


# --- brand surfaces -------------------------------------------------------------------------------
def _wordmark_text() -> Text:
    return Text(wordmark.wordmark(), style="eddy.brand")


def wake_screen(runs: Sequence[dict] | None = None) -> RenderableType:
    """The `eddy` wake splash: the eagle + italic EDDY wordmark + tagline + a short next-step hint.

    `runs` (optional, newest first) renders as a tiny fleet line; pass None to omit it.
    """
    right: list[RenderableType] = [_wordmark_text(), Text.from_markup(wordmark.tagline()), Text("")]
    if runs:
        recent = ", ".join(f"{r.get('slug', '?')} [eddy.dim]({r.get('phase', '?')})[/eddy.dim]" for r in runs[:2])
        right.append(Text.from_markup(f"[eddy.dim]recent:[/eddy.dim] {recent}"))
        right.append(Text(""))
    for cmd, what in (
        ("eddy run <footage>", "start a full edit"),
        ("eddy doctor", "check your setup"),
        ("eddy runs", "list recent runs"),
        ("eddy --help", "every command"),
    ):
        right.append(Text.from_markup(f"[eddy.accent]▸[/eddy.accent] [bold]{cmd:<20}[/bold] [eddy.dim]{what}[/eddy.dim]"))

    grid = Table.grid(padding=(0, 3))
    grid.add_column(justify="center", vertical="middle")
    grid.add_column(vertical="middle")
    grid.add_row(sprite_renderable("idle"), Group(*right))
    return Panel(grid, border_style="eddy.accent", padding=(1, 2), title="[eddy.brand]EDDY[/eddy.brand]", title_align="left")


def banner(subtitle: str | None = None) -> RenderableType:
    """A compact one-line brand header for subcommands: mini eagle mark + EDDY + optional subtitle."""
    line = f"{sprite.MINI}  [eddy.brand]EDDY[/eddy.brand]"
    if subtitle:
        line += f"  [eddy.dim]· {subtitle}[/eddy.dim]"
    return Text.from_markup(line)


def panel(body: RenderableType, title: str | None = None, style: str = "eddy.accent") -> None:
    console().print(Panel(body, title=title, border_style=style, padding=(0, 1)))


# Status helpers build Rich Text rather than interpolating into markup, so a message containing
# brackets (a path, an exception repr) can never break rendering or inject styling.
def ok(msg: str) -> None:
    console().print(Text.assemble(("✓ ", "eddy.ok"), msg))


def warn(msg: str) -> None:
    console().print(Text.assemble(("⚠ ", "eddy.warn"), msg))


def err(msg: str) -> None:
    console().print(Text.assemble(("✗ ", "eddy.err"), msg))


def note(msg: str) -> None:
    console().print(Text(msg, style="eddy.dim"))


@contextmanager
def progress(transient: bool = False) -> Iterator[Progress]:
    """A themed Rich progress bar (spinner + bar + % + ETA). Use for bounded, measurable phases."""
    prog = Progress(
        SpinnerColumn(style="eddy.accent"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="eddy.accent", finished_style="eddy.ok"),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console(),
        transient=transient,
    )
    with prog:
        yield prog
