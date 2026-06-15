"""v0.8: writing-script detection for an honest caption guard.

eddy's burned word-captions are drawn left-to-right, word by word, with Pillow and no text shaping
(no bidi reordering, no Arabic contextual joining). That's fine for Latin/Cyrillic/Greek but renders
RTL scripts incorrectly and needs a CJK-capable font for CJK glyphs. We don't silently ship broken
captions: detect the script and warn, pointing at the sidecar .srt/.vtt (shaped by the player) as
the correct fallback. This is an honest guard, not RTL shaping support."""

from __future__ import annotations

# Unicode blocks. RTL: Hebrew, Arabic (+ supplements / presentation forms), Syriac, Thaana, NKo.
_RTL_RANGES = [
    (0x0590, 0x05FF), (0x0600, 0x06FF), (0x0700, 0x074F), (0x0750, 0x077F),
    (0x0780, 0x07BF), (0x07C0, 0x07FF), (0x08A0, 0x08FF), (0xFB1D, 0xFDFF), (0xFE70, 0xFEFF),
]
# CJK: Hiragana/Katakana, CJK Unified (+ ext A), Hangul syllables, CJK compatibility.
_CJK_RANGES = [
    (0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF),
]
# Common bundled/system fonts that lack RTL shaping and CJK glyphs.
_LATIN_ONLY_FONT_HINTS = ("dejavu", "liberation")


def _in_ranges(ch: str, ranges: list[tuple[int, int]]) -> bool:
    cp = ord(ch)
    return any(a <= cp <= b for a, b in ranges)


def has_rtl(text: str) -> bool:
    return any(_in_ranges(c, _RTL_RANGES) for c in text)


def has_cjk(text: str) -> bool:
    return any(_in_ranges(c, _CJK_RANGES) for c in text)


def caption_script_warnings(text: str, font_path: str | None = None) -> list[str]:
    """Warnings (possibly empty) about scripts the burned-caption renderer can't render correctly."""
    warns: list[str] = []
    if has_rtl(text):
        warns.append(
            "RTL script (Arabic/Hebrew/…) detected: burned word-captions don't do bidi reordering "
            "or contextual shaping and will render incorrectly. Use the sidecar .srt/.vtt (shaped by "
            "the player) for correct RTL captions."
        )
    if has_cjk(text):
        fp = (font_path or "").lower()
        if not fp or any(h in fp for h in _LATIN_ONLY_FONT_HINTS):
            warns.append(
                "CJK script detected but the caption font likely lacks CJK glyphs (install Noto Sans "
                "CJK, or rely on the sidecar .srt/.vtt). Burned captions may show empty boxes."
            )
    return warns
