"""Karaoke caption rendering: word-state PNGs + qtrle overlay layer.

Port of the caption core of vendor render_redesigned_shorts_batch.py:
3-6 word cues, past words bright, current word on a blue rounded highlight,
future words dim — per the approved standard."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from eddy.media.ffmpeg import run_ffmpeg, video_encoder_args
from eddy.render import layout as L

FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/SFNS.ttf",
    # Linux (Debian/Ubuntu/Fedora/Arch common locations)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]

_FONT_DIRS = [
    "/usr/share/fonts", "/usr/local/share/fonts", "/Library/Fonts",
    "C:/Windows/Fonts",
]
_font_warned = [False]
_script_warned = [False]


def _find_font() -> str | None:
    for c in FONT_CANDIDATES:
        if Path(c).exists():
            return c
    # nothing in the known list — glob the standard font dirs for any TrueType (prefer bold sans)
    import glob
    import os

    for d in _FONT_DIRS + [str(Path.home() / ".fonts"), str(Path.home() / "Library" / "Fonts")]:
        if not os.path.isdir(d):
            continue
        for pat in ("**/*Bold*.ttf", "**/*.ttf"):
            hits = sorted(glob.glob(os.path.join(d, pat), recursive=True))
            if hits:
                return hits[0]
    return None


def load_font(size: int) -> ImageFont.FreeTypeFont:
    path = _find_font()
    if path:
        return ImageFont.truetype(path, size=size)
    # No system font: Pillow's load_default(size) is a real scalable font on modern Pillow (fine for
    # Latin; non-Latin needs a real font — v0.7). Warn once so it's not a silent quality drop.
    if not _font_warned[0]:
        print("[eddy] WARNING: no system TrueType font found; captions use Pillow's default font. "
              "Install a font (e.g. DejaVu) for best caption quality.", file=sys.stderr)
        _font_warned[0] = True
    return ImageFont.load_default(size=size)  # type: ignore[return-value]


def word_width(word: str, font: ImageFont.FreeTypeFont) -> int:
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = probe.textbbox((0, 0), word.upper(), font=font, stroke_width=2)
    return int(bbox[2] - bbox[0])


def group_cues(words: list[dict]) -> list[list[dict]]:
    font = load_font(L.CAPTION_FONT_S)
    cues: list[list[dict]] = []
    current: list[dict] = []
    width = 0
    for w in words:
        text = str(w["word"]).strip()
        next_width = width + word_width(text, font) + (24 if current else 0)
        duration = float(w["end"]) - float(current[0]["start"]) if current else 0.0
        if current and (len(current) >= L.CUE_MAX_WORDS or duration >= L.CUE_MAX_S or next_width > L.CUE_MAX_PX):
            cues.append(current)
            current, width = [], 0
        current.append(w)
        width += word_width(text, font) + (24 if len(current) > 1 else 0)
    if current:
        cues.append(current)
    return cues


def render_caption_png(path: Path, cue: list[dict], current_idx: int) -> None:
    font = load_font(L.CAPTION_FONT_S)
    words = [str(w["word"]).strip().upper() for w in cue]
    widths = [word_width(w, font) for w in words]
    gap = 22
    total = sum(widths) + gap * (len(words) - 1)
    if total > 960:
        font = load_font(L.CAPTION_FONT_XS)
        widths = [word_width(w, font) for w in words]
        gap = 18
        total = sum(widths) + gap * (len(words) - 1)

    img = Image.new("RGBA", (L.W, L.CAPTION_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x = math.floor((L.W - total) / 2)
    y = max(18, math.floor((L.CAPTION_H - font.size) / 2) - 2)
    for idx, word in enumerate(words):
        w_px = widths[idx]
        if idx == current_idx:
            draw.rounded_rectangle(
                (x - 16, y - 12, x + w_px + 16, y + font.size + 18), radius=20, fill=L.HIGHLIGHT_BLUE
            )
            fill, stroke, sw = (255, 255, 255, 255), L.STROKE_DARK, 3
        elif idx < current_idx:
            fill, stroke, sw = L.WORD_SPOKEN, L.STROKE_DARK, 3
        else:
            fill, stroke, sw = L.WORD_FUTURE, L.STROKE_DIM, 2
        draw.text((x, y), word, font=font, fill=fill, stroke_width=sw, stroke_fill=stroke)
        x += w_px + gap
    img.save(path)


def caption_events(asset_dir: Path, output_words: list[dict]) -> list[dict]:
    """output_words carry OUTPUT-timeline start/end. One PNG per word-state."""
    cue_dir = asset_dir / "caption-states"
    cue_dir.mkdir(parents=True, exist_ok=True)
    if not _script_warned[0]:  # honest guard: RTL/CJK can't render correctly in burned captions
        from eddy.render.scripts import caption_script_warnings

        text = " ".join(str(w.get("word", "")) for w in output_words)
        for warning in caption_script_warnings(text, _find_font()):
            print(f"[eddy] ⚠ {warning}", file=sys.stderr)
        _script_warned[0] = True
    events: list[dict] = []
    prev_end = 0.0
    for ci, cue in enumerate(group_cues(output_words)):
        for wi, w in enumerate(cue):
            start = max(float(w["start"]), prev_end)
            next_start = float(cue[wi + 1]["start"]) if wi + 1 < len(cue) else float(w["end"]) + 0.24
            end = max(next_start, start + 0.12)
            path = cue_dir / f"caption-{ci:03d}-{wi:02d}.png"
            render_caption_png(path, cue, wi)
            events.append({"start": start, "end": end, "path": path})
            prev_end = end
    return events


def _q(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def make_caption_layer(out_dir: Path, events: list[dict], total_duration: float, run_dir: Path) -> Path:
    blank = out_dir / "caption-blank.png"
    Image.new("RGBA", (L.W, L.CAPTION_H), (0, 0, 0, 0)).save(blank)
    layer = out_dir / "captions.mov"
    lines = ["ffconcat version 1.0"]
    cursor = 0.0
    for ev in events:
        if ev["start"] > cursor + 0.01:
            lines += [f"file '{_q(blank)}'", f"duration {ev['start'] - cursor:.3f}"]
        lines += [f"file '{_q(Path(ev['path']))}'", f"duration {max(0.04, ev['end'] - ev['start']):.3f}"]
        cursor = ev["end"]
    if total_duration > cursor + 0.01:
        lines += [f"file '{_q(blank)}'", f"duration {total_duration - cursor:.3f}"]
    lines.append(f"file '{_q(blank)}'")
    concat_file = out_dir / "captions.ffconcat"
    concat_file.write_text("\n".join(lines) + "\n")
    run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(concat_file), "-vf", "fps=25,format=argb", "-c:v", "qtrle", str(layer)],
        run_dir=run_dir,
    )
    return layer


def burn_captions(base: Path, final: Path, events: list[dict], total_duration: float, out_dir: Path, run_dir: Path, caption_y: int | None = None) -> Path:
    layer = make_caption_layer(out_dir, events, total_duration, run_dir)
    run_ffmpeg(
        [
            "-i", str(base), "-i", str(layer),
            "-filter_complex", f"[0:v][1:v]overlay=0:{L.CAPTION_Y if caption_y is None else caption_y}:format=auto[v]",
            "-map", "[v]", "-map", "0:a",
            *video_encoder_args("7500k"),
            "-c:a", "copy", "-shortest", "-movflags", "+faststart",
            "-t", f"{total_duration:.3f}", str(final),
        ],
        run_dir=run_dir,
    )
    return final
