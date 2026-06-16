"""The EDDY wordmark — a bold, upright 8-bit block logo.

Hand-built from block glyphs (no figlet/pyfiglet dependency, so it works offline and adds no install
weight). Upright, not italic; the heavy ``█`` blocks match the sprite's pixel look. `wordmark()`
returns the art; `tagline()` returns the strapline.
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


def wordmark(word: str = "EDDY") -> str:
    """The upright 8-bit block wordmark for `word` (defaults to EDDY)."""
    return "\n".join(_assemble(word))


def tagline() -> str:
    """Rich-markup strapline shown under the wordmark on the wake screen."""
    return (
        "[italic eddy.dim]local-first agentic video editor[/italic eddy.dim]"
        "  [eddy.dim]·[/eddy.dim]  "
        f"[eddy.accent]v{__version__}[/eddy.accent]"
    )
