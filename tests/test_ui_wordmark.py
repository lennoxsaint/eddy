"""The EDDY wordmark: sheared block letters, dep-free, plus the version tagline."""

from __future__ import annotations

from eddy.ui import wordmark


def test_wordmark_is_five_rows():
    lines = wordmark.wordmark().splitlines()
    assert len(lines) == 5


def test_wordmark_is_upright_not_sheared():
    lines = wordmark.wordmark().splitlines()
    lead = [len(line) - len(line.lstrip(" ")) for line in lines]
    # upright: the first glyph column (E) is flush-left on every row — no per-row italic indent
    assert lead[0] == lead[-1] == 0
    assert max(lead) == 0


def test_wordmark_uses_block_glyph():
    assert "█" in wordmark.wordmark()


def test_tagline_carries_version_and_markup():
    tag = wordmark.tagline()
    assert "agentic video editor" in tag
    assert "eddy.accent" in tag  # version styled with the brand accent
