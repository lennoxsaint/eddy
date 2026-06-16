"""Eddy the chibi eaglet — the mascot sprite, as pixel-art bitmaps.

Design brief (locked with Lennox): a CUTE, kawaii baby bald eaglet — a big round white fluffy head,
huge sparkly eyes, blush cheeks, a small hooked gold beak, a chubby brown body, gold feet. Iterated
against rendered PNGs until it reads as an unmistakably-adorable baby eagle (cuter than the v1.1
realistic bust, which read as stern).

Art is data. Each bitmap is a list of equal-width strings of palette keys (see `pixels.PALETTE`);
``.`` and spaces are transparent. Two sizes ship — `HERO` (wake screen / TUI header) and `SMALL`
(inline / compact). Emotional states are built by overriding only the eye rows of the base bitmap
(`_EXPR`), so the art stays a small, reviewable diff. `MINI` is a one-line mark; `ASCII` is the
no-colour fallback (half-blocks need colour to read).
"""

from __future__ import annotations

STATES: tuple[str, ...] = ("idle", "thinking", "working", "success", "error")

# A one-line stylised eaglet face for compact, single-line headers.
MINI = "[eddy.eye]•[/eddy.eye][eddy.beak]ᵥ[/eddy.beak][eddy.eye]•[/eddy.eye]"

# Plain-ASCII fallback for no-colour terminals (half-block pixels are unreadable without colour).
ASCII = r"""
  .---.
 ( o o )
  `>v<`
"""


def ascii_art() -> str:
    """The plain-text eaglet fallback, blank lines trimmed."""
    return ASCII.strip("\n")


# --- base bitmaps (idle) --------------------------------------------------------------------------
# HERO: ~21x23 px chibi baby bald eaglet, front-facing.
HERO: list[str] = [
    ".......WWWWWWWW.......",
    ".....WWWWWWWWWWWW.....",
    "....WWWWWWWWWWWWWW....",
    "...WWWWWWWWWWWWWWWW...",
    "..WWWWWWWWWWWWWWWWWW..",
    "..WWWWWWWWWWWWWWWWWW..",
    ".WWWWWWWWWWWWWWWWWWWW.",
    ".WWW.KK.WWWWWW.KK.WWW.",
    ".WWWKHKKWWWWWWKHKKWWW.",
    ".WWWKKKKWWWWWWKKKKWWW.",
    ".WWWKKKKWWWWWWKKKKWWW.",
    ".WWpWKKWWGGGGWKKWpWWW.",
    ".WWppWWWWGGGgWWWppWWW.",
    "..WWWWWWWrGGgWWWWWWW..",
    "...WWWWWWWGggWWWWWWW..",
    "....WWWWWWWggWWWWWW...",
    ".....DDDDDDDDDDDD.....",
    "....DDBbBBBBBBbBDD....",
    "...DDBBBBBBBBBBBBDD...",
    "...DBBBBBBBBBBBBBBD...",
    "...DBBBBBBBBBBBBBBD...",
    "....DBBBBBBBBBBBBD....",
    ".....DDDDDDDDDDDD.....",
    ".......GG....GG.......",
]

# SMALL: ~14x15 px, the same eaglet compressed for inline / TUI-header / animation use.
SMALL: list[str] = [
    "....WWWWWW....",
    "..WWWWWWWWWW..",
    ".WWWWWWWWWWWW.",
    ".WWWWWWWWWWWW.",
    ".WWHKKWWHKKWW.",
    ".WWKKKWWKKKWW.",
    ".WWKKKWWKKKWW.",
    ".WppWWGGWWppW.",
    "..WWWGGgWWWW..",
    "...WWWggWWW...",
    "....DDDDDDD...",
    "...DBBBBBBBD..",
    "...DBBBBBBBD..",
    "....DDDDDDD...",
    ".....G.G.....",
]

# Per-size expression overrides: {row_index: replacement_row}. Only the changed rows are listed; a
# state is the base bitmap with these rows swapped in. Keeps each mood a tiny, reviewable diff.
_HERO_EXPR: dict[str, dict[int, str]] = {
    "blink": {
        7: ".WWWWWWWWWWWWWWWWWWWW.",
        8: ".WWWWWWWWWWWWWWWWWWWW.",
        9: ".WWWKKKKWWWWWWKKKKWWW.",
        10: ".WWWWWWWWWWWWWWWWWWWW.",
        11: ".WWpWWWWWGGGGWWWWpWWW.",
    },
    "focus": {  # determined: same big eyes, sparkle off
        8: ".WWWKKKKWWWWWWKKKKWWW.",
    },
    "happy": {
        7: ".WWWWWWWWWWWWWWWWWWWW.",
        8: ".WWW.KK.WWWWWW.KK.WWW.",
        9: ".WWWK..KWWWWWWK..KWWW.",
        10: ".WWWWWWWWWWWWWWWWWWWW.",
        11: ".WWpWWWWWGGGGWWWWpWWW.",
    },
    "sad": {
        7: ".WWWWWWWWWWWWWWWWWWWW.",
        8: ".WWWWWWWWWWWWWWWWWWWW.",
        9: ".WWWK..KWWWWWWK..KWWW.",
        10: ".WWW.KK.WWWWWW.KK.WWW.",
        11: ".WWpwKKWWGGGGWKKwpWWW.",
    },
    "think": {  # base eyes + a little thought dot up to the right
        1: ".....WWWWWWWWWWWW..W..",
        2: "....WWWWWWWWWWWWWW.w..",
    },
}

_SMALL_EXPR: dict[str, dict[int, str]] = {
    "blink": {
        4: ".WWWWWWWWWWWW.",
        5: ".WWKKKWWKKKWW.",
        6: ".WWWWWWWWWWWW.",
    },
    "focus": {
        4: ".WWKKKWWKKKWW.",
    },
    "happy": {
        4: ".WW.K.WW.K.WW.",
        5: ".WWK.KWWK.KWW.",
        6: ".WWWWWWWWWWWW.",
    },
    "sad": {
        4: ".WWWWWWWWWWWW.",
        5: ".WWK.KWWK.KWW.",
        6: ".WW.K.WW.K.WW.",
        7: ".WpwWGGWWpwW..",
    },
    "think": {
        1: "..WWWWWWWWWWw.",
    },
}


def _expr(base: list[str], overrides: dict[int, str]) -> list[str]:
    """The base bitmap with the given rows replaced (an expression edit)."""
    out = list(base)
    for r, row in overrides.items():
        if 0 <= r < len(out):
            out[r] = row
    return out


def _build(base: list[str], expr: dict[str, dict[int, str]]) -> dict[str, list[list[str]]]:
    blink = _expr(base, expr["blink"])
    focus = _expr(base, expr["focus"])
    return {
        "idle": [base, blink],
        "thinking": [_expr(base, expr["think"]), base],
        "working": [focus, blink],
        "success": [_expr(base, expr["happy"])],
        "error": [_expr(base, expr["sad"])],
    }


_HERO_STATES = _build(HERO, _HERO_EXPR)
_SMALL_STATES = _build(SMALL, _SMALL_EXPR)


def frames(state: str = "idle", small: bool = False) -> list[list[str]]:
    """The animation loop (one or more bitmaps) for a state. Unknown state falls back to idle."""
    table: dict[str, list[list[str]]] = _SMALL_STATES if small else _HERO_STATES
    return table.get(state) or table["idle"]


def frame(state: str = "idle", index: int = 0, small: bool = False) -> list[str]:
    """A single bitmap frame; `index` wraps so an animator can advance forever."""
    loop = frames(state, small=small)
    return loop[index % len(loop)]
