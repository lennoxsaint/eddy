"""v0.8: RTL/CJK caption guard — burned word-captions can't bidi-reshape RTL or render CJK without a
CJK font, so detect the script and warn (pointing at the sidecar .srt/.vtt) rather than ship broken
captions silently."""

from eddy.render.scripts import caption_script_warnings, has_cjk, has_rtl


def test_latin_text_no_warnings():
    assert has_rtl("Hello world") is False
    assert has_cjk("Hello world") is False
    assert caption_script_warnings("Hello world, this is a normal caption.") == []


def test_rtl_detected_and_warned():
    arabic = "مرحبا بكم في القناة"  # "welcome to the channel"
    assert has_rtl(arabic) is True
    warns = caption_script_warnings(arabic)
    assert any("RTL" in w and "sidecar" in w for w in warns)


def test_hebrew_is_rtl():
    assert has_rtl("שלום עולם") is True


def test_cjk_warns_on_latin_only_font():
    jp = "こんにちは世界"
    assert has_cjk(jp) is True
    warns = caption_script_warnings(jp, font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    assert any("CJK" in w for w in warns)


def test_cjk_no_warn_with_cjk_font():
    jp = "こんにちは世界"
    warns = caption_script_warnings(jp, font_path="/usr/share/fonts/noto/NotoSansCJK-Bold.otf")
    assert warns == []  # a CJK-capable font: no glyph warning
