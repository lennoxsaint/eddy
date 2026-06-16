"""The EDDY wordmark — a bold 8-bit block logo, sheared into an italic lean.

Hand-built from upright block glyphs and sheared in code (no figlet/pyfiglet dependency, so it works
offline and adds no install weight). The lean gives the "italicised capitalised EDDY" Lennox asked
for when you wake Eddy in the terminal, and the heavy ``█`` blocks match the sprite's pixel look.
`wordmark()` returns the art; `tagline()` returns the Rich-italic strapline.
"""

from __future__ import annotations

from eddy import __version__

# Upright 5-row block glyphs, each 5 columns wide. Assembled with one-space gaps, then sheared.
_GLYPHS: dict[str, list[str]] = {
    "E": ["█████", "█    ", "████ ", "█    ", "█████"],
    "D": ["████ ", "█   █", "█   █", "█   █", "████ "],
    "Y": ["█   █", " █ █ ", "  █  ", "  █  ", "  █  "],
}
_ROWS = 5


def _assemble(word: str) -> list[str]:
    rows = []
    for r in range(_ROWS):
        rows.append(" ".join(_GLYPHS[ch][r] for ch in word))
    return rows


def _shear(rows: list[str]) -> list[str]:
    """Lean the block right: indent the top row most, the bottom row not at all → italic slant."""
    n = len(rows)
    return [(" " * (n - 1 - i)) + row for i, row in enumerate(rows)]


def wordmark(word: str = "EDDY") -> str:
    """The sheared block wordmark for `word` (defaults to EDDY)."""
    return "\n".join(_shear(_assemble(word)))


def tagline() -> str:
    """Rich-markup strapline shown under the wordmark on the wake screen."""
    return (
        "[italic eddy.dim]local-first agentic video editor[/italic eddy.dim]"
        "  [eddy.dim]·[/eddy.dim]  "
        f"[eddy.accent]v{__version__}[/eddy.accent]"
    )
