"""Eddy the bald eagle — the mascot sprite, as pixel-art bitmaps.

Box-drawing glyphs can't actually look like an eagle (a front face with two round eyes reads as an
owl), so Eddy is a real palette-indexed *bitmap* rendered with the half-block technique in
`eddy.ui.pixels`. The design was iterated against rendered PNGs until it unmistakably reads as a
bald eagle: white head, yellow eye under a brow, a hooked gold beak with a dark gape line, a brown
folded-wing body with a feathered hem, and gold talons — chunky and cute, not fierce.

Two sizes ship — `HERO` (wake screen) and `SMALL` (run phases, the animator, success/error) — plus
`MINI`, a one-line stylised mark for inline prefixes where a multi-row sprite won't fit. Emotional
states are small pixel edits on the base bitmap; callers reinforce them with coloured status text
(spinner / ✓ / ✗). A bitmap is a list of equal-width strings of palette keys (see `pixels.PALETTE`);
``.`` and spaces are transparent.
"""

from __future__ import annotations

STATES: tuple[str, ...] = ("idle", "thinking", "working", "success", "error")

# A one-line stylised eagle mark for compact, single-line headers (the hero won't fit on a line).
MINI = "[eddy.crown]ʌ[/eddy.crown][eddy.eye]•[/eddy.eye][eddy.beak]ᗨ[/eddy.beak]"

# Half-block pixel art needs colour to read; on a no-colour terminal it collapses to a blob. This
# plain-ASCII eagle is the fallback there (and in piped output).
ASCII = r"""
   __
  ( o\___
   \    .>
   /__\\
"""


def ascii_art() -> str:
    """The plain-text eagle fallback, blank lines trimmed."""
    return ASCII.strip("\n")


# --- base bitmaps (idle) --------------------------------------------------------------------------
# HERO: ~27x26 px bald-eagle bust on a chunky body, head in profile facing right.
HERO: list[str] = [
    "        WWWWWWWW            ",
    "      WWWWWWWWWWWW          ",
    "     WWWWWWWWWWWWWW         ",
    "    WWWWWWWWWWWWWWWW        ",
    "   WWWWWWWWWWWWWWWWWW       ",
    "   WWWWWWWWWWWKKKWWWWW      ",
    "  WWWWWWWWWWWWKYYKWGGGGGGG  ",
    "  WWWWWWWWWWWWKKKWGGGGGGGG  ",
    "  WWWWWWWWWWWWWWWWGGGGGGGGG ",
    "  WWWWWWWWWWWWWWWWrrrrrrGGG ",
    "   WWWWWWWWWWWWWWW GGGGGGGg ",
    "   WWWWWWWWWWWWWWW    GGGg  ",
    "    WWWWWWWWWWWWWw     Gg   ",
    "    wWWWWWWWWWWWWw          ",
    "     wwWWWWWWWWw            ",
    "      DDDDDDDDDD            ",
    "     DDBBBBBBBBBD           ",
    "    DDBBBDBBBBBBD           ",
    "   DDBBBBDBBBBBBD           ",
    "   DBBBBBDBBBBBBD           ",
    "   DBBBBBBDBBBBBD           ",
    "   DBBBBBBBDBBBBD           ",
    "    DBDBDBDBDBDBD           ",
    "    DDDDDDDDDDDD            ",
    "      WWWWWWWW              ",
    "      GG    GG              ",
]

# SMALL: ~16x16 px, same eagle compressed for inline / phase / animation use.
SMALL: list[str] = [
    "    WWWWWW      ",
    "   WWWWWWWW     ",
    "  WWWWWWWWWW    ",
    "  WWWWWKKWWWW   ",
    "  WWWWKYKWGGGG  ",
    "  WWWWKKKWGGGGg ",
    "  WWWWWWWrrGGGg ",
    "   WWWWWWWWGGg  ",
    "   wWWWWWWWg    ",
    "    DDDDDDD     ",
    "   DDBBDBBDD    ",
    "  DDBBBDBBBDD   ",
    "  DBBBDBBBBD    ",
    "   DBDBDBDBD    ",
    "   DDDDDDDD     ",
    "     GG GG      ",
]

Edit = tuple[int, int, str]


def _apply(base: list[str], edits: list[Edit]) -> list[str]:
    """Return a copy of `base` with `(row, col, char)` pixel edits applied."""
    rows = [list(line) for line in base]
    for r, c, ch in edits:
        if 0 <= r < len(rows) and 0 <= c < len(rows[r]):
            rows[r][c] = ch
    return ["".join(row) for row in rows]


# --- state frames ---------------------------------------------------------------------------------
# Each state is a list of bitmap frames (the animation loop). Expressions are small eye/accent edits;
# the working flap toggles a couple of wing-highlight pixels so Eddy looks busy without flicker.
def _states(base: list[str], eye: tuple[int, int]) -> dict[str, list[list[str]]]:
    er, ec = eye  # eye centre (the yellow iris pixel)
    blink = _apply(base, [(er, ec, "K")])
    focus = _apply(base, [(er, ec, "K")])  # focused: dark pupil, no yellow glint
    think = _apply(base, [(er, ec - 1, "K"), (er, ec, "Y"), (er - 4, ec + 6, "w"), (er - 5, ec + 8, "W")])
    happy = _apply(base, [(er - 1, ec - 1, "K"), (er - 1, ec + 1, "K"), (er, ec - 1, "W"), (er, ec, "K"), (er, ec + 1, "W")])
    sad = _apply(base, [(er, ec, "K"), (er + 1, ec - 1, "K"), (er + 1, ec + 1, "K")])
    return {
        "idle": [base, blink],
        "thinking": [think, base],
        "working": [focus, _apply(focus, [])],
        "success": [happy],
        "error": [sad],
    }


_HERO_STATES = _states(HERO, eye=(6, 14))
_SMALL_STATES = _states(SMALL, eye=(4, 7))


def frames(state: str = "idle", small: bool = False) -> list[list[str]]:
    """The animation loop (one or more bitmaps) for a state. Unknown state falls back to idle."""
    table: dict[str, list[list[str]]] = _SMALL_STATES if small else _HERO_STATES
    return table.get(state) or table["idle"]


def frame(state: str = "idle", index: int = 0, small: bool = False) -> list[str]:
    """A single bitmap frame; `index` wraps so an animator can advance forever."""
    loop = frames(state, small=small)
    return loop[index % len(loop)]
