"""v0.6: cross-platform caption fonts — Windows/Linux candidates + glob fallback + non-silent
fallback to Pillow's (real, scalable) default. No more macOS-only font loading."""

from PIL import ImageFont

from eddy.render import captions


def test_font_candidates_cover_all_platforms():
    joined = " ".join(captions.FONT_CANDIDATES)
    assert "/System/Library/Fonts" in joined          # macOS
    assert "/usr/share/fonts" in joined                # Linux
    assert "C:/Windows/Fonts" in joined                # Windows


def test_find_font_resolves_on_this_machine():
    # this dev machine has system fonts, so a real path is found (not None)
    assert captions._find_font() is not None


def test_load_font_returns_real_scalable_font():
    f = captions.load_font(40)
    assert isinstance(f, ImageFont.FreeTypeFont)


def test_load_font_warns_and_falls_back_when_no_system_font(monkeypatch, capsys):
    monkeypatch.setattr(captions, "_find_font", lambda: None)
    captions._font_warned[0] = False
    f = captions.load_font(40)
    assert isinstance(f, ImageFont.FreeTypeFont)  # Pillow default is a real font, not tofu
    assert "no system TrueType font" in capsys.readouterr().err  # warned, not silent
