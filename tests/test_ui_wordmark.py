"""The EDDY wordmark: sheared block letters, dep-free, plus the version tagline."""

from __future__ import annotations

from eddy.ui import wordmark


def test_wordmark_is_five_rows():
    lines = wordmark.wordmark().splitlines()
    assert len(lines) == 5


def test_wordmark_is_sheared_top_row_indented_most():
    lines = wordmark.wordmark().splitlines()
    lead = [len(line) - len(line.lstrip(" ")) for line in lines]
    assert lead[0] > lead[-1]  # italic lean: top pushed right, bottom flush
    assert lead == sorted(lead, reverse=True)


def test_wordmark_uses_block_glyph():
    assert "█" in wordmark.wordmark()


def test_tagline_carries_version_and_markup():
    tag = wordmark.tagline()
    assert "agentic video editor" in tag
    assert "eddy.accent" in tag  # version styled with the brand accent
