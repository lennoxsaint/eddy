#!/usr/bin/env python3
"""Karaoke ASS burner — the clean V1 "anchor" look, self-contained.

Builds an .ass subtitle with per-word highlight (current word on a cyan fill, spoken words white,
upcoming dimmed — the frozen style in layout-constants.md) and burns it with ffmpeg. Used for the
Shorts caption strip, where `embedded-captions` (talking-head matting) doesn't fit the split stack.

One Dialogue event per word-state gives exact control and stays calm (never a per-word storm):
≤`--max-words` words on screen at once, the current word highlighted.

Usage:
  karaoke_ass.py --transcript short.words.json --out short.ass \
      [--play-w 1080 --play-h 1920 --y 1155 --font-size 52 --max-words 4 --uppercase]
  karaoke_ass.py ... --burn --in short.mp4 --video-out short_cap.mp4    # also burns

transcript.words.json: {"words":[{"word","start","end"},...]} (edited-timeline timings).
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

# ASS colours are &HAABBGGRR. From layout-constants.md:
WHITE = "&H00FFFFFF"          # spoken words
CYAN = "&H00FFA34A"           # current word (RGBA 74,163,255)
DIM = "&H00A09184"            # upcoming words (RGBA 132,145,160)
STROKE = "&H00160A01"         # dark navy outline


def esc(t: str) -> str:
    # strip ASS control chars + surrounding punctuation (clean caption look, no stray commas)
    t = t.replace("\\", "").replace("{", "(").replace("}", ")").strip()
    return t.strip(",.;:!?—–\"'").strip() or t


def cues(words, max_words, max_dur=2.0):
    """Group words into small cues (≤max_words, ≤max_dur)."""
    out, cur = [], []
    for w in words:
        if not cur:
            cur = [w]
            continue
        if len(cur) >= max_words or (w["end"] - cur[0]["start"]) > max_dur:
            out.append(cur); cur = [w]
        else:
            cur.append(w)
    if cur:
        out.append(cur)
    return out


def ts(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _line_w(text: str, fs: int, upper: bool) -> float:
    """Conservative rendered-width estimate for Arial (over-estimates slightly so we never clip)."""
    factor = 0.60 if upper else 0.55
    return len(text) * fs * factor


def fit_cue(texts: list[str], fs: int, max_w: float, upper: bool, font_min: int) -> tuple[int, int | None]:
    """Return (font_size, break_index) so the cue fits inside `max_w` (the safe-area width).

    First shrink the font (down to font_min); if a single line still overruns at the floor, wrap into
    two balanced lines and shrink to the widest of the two. Guarantees no glyph crosses the margin.
    """
    joined = " ".join(texts)
    if _line_w(joined, fs, upper) <= max_w:
        return fs, None
    ideal1 = int(max_w / (_line_w(joined, 1, upper) or 1))     # px that fits the whole cue on one line
    fits_at_floor = _line_w(joined, max(font_min, ideal1), upper) <= max_w
    if fits_at_floor or len(texts) < 2:
        # one line: shrink to font_min if that fits; a lone unbreakable token drops BELOW the floor so
        # no glyph ever crosses the margin (absolute no-clip beats the legibility floor for that case).
        return (min(fs, max(font_min, ideal1)) if fits_at_floor else max(8, min(fs, ideal1))), None
    # still too wide at the floor -> wrap into two char-balanced lines
    best_brk, best_diff = 1, 10 ** 9
    for brk in range(1, len(texts)):
        diff = abs(len(" ".join(texts[:brk])) - len(" ".join(texts[brk:])))
        if diff < best_diff:
            best_diff, best_brk = diff, brk
    widest = max(" ".join(texts[:best_brk]), " ".join(texts[best_brk:]), key=len)
    ideal = int(max_w / (_line_w(widest, 1, upper) or 1))
    # normally floor at font_min; but if a single unbreakable token is wider than the safe area even
    # at font_min, drop BELOW the floor for that cue so no glyph ever crosses the margin (the absolute
    # no-clip guarantee wins over the legibility floor for a pathological long word).
    line_fs = max(font_min, min(fs, ideal)) if ideal >= font_min else max(8, ideal)
    return line_fs, best_brk


def build(words, w, h, y, fs, max_words, upper, margin=60, font_min=52):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: kar,Arial,{fs},{WHITE},{WHITE},{STROKE},&H64000000,-1,0,0,0,100,100,0,0,1,3,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # flatten so each word-state ends exactly when the NEXT word starts — never linger into the next
    # cue (overlapping Dialogues at the same \pos double-render and look garbled).
    cue_list = cues(words, max_words)
    # Safe-area fit per cue: shrink font (to font_min) then wrap to 2 lines so nothing clips the frame.
    max_w = w - 2 * margin
    fit = {}
    for ci, cue in enumerate(cue_list):
        texts = [(esc(ww["word"]).upper() if upper else esc(ww["word"])) for ww in cue]
        fit[ci] = fit_cue(texts, fs, max_w, upper, font_min)
    flat = [(ci, i, cw) for ci, cue in enumerate(cue_list) for i, cw in enumerate(cue)]
    lines = []
    for gi, (ci, i, cw) in enumerate(flat):
        cue = cue_list[ci]
        cue_fs, brk = fit[ci]
        parts = []
        for j, ww in enumerate(cue):
            txt = esc(ww["word"])
            if upper:
                txt = txt.upper()
            if j < i:
                parts.append(f"{{\\c{WHITE}}}{txt}")
            elif j == i:
                parts.append(f"{{\\c{CYAN}\\b1}}{txt}{{\\b0}}")
            else:
                parts.append(f"{{\\c{DIM}}}{txt}")
        if brk:
            body = " ".join(parts[:brk]) + "\\N" + " ".join(parts[brk:])
        else:
            body = " ".join(parts)
        fs_tag = f"\\fs{cue_fs}" if cue_fs != fs else ""
        text = "{\\pos(%d,%d)\\an5%s}" % (w // 2, y, fs_tag) + body
        start = cw["start"]
        end = flat[gi + 1][2]["start"] if gi + 1 < len(flat) else cw["end"] + 0.12
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},kar,,0,0,0,,{text}")
    return head + "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--play-w", type=int, default=1080)
    ap.add_argument("--play-h", type=int, default=1920)
    ap.add_argument("--y", type=int, default=1155)
    ap.add_argument("--font-size", type=int, default=68)  # bumped from 52 — mobile Shorts legibility
    ap.add_argument("--font-min", type=int, default=52, help="floor for the safe-area auto-shrink")
    ap.add_argument("--margin", type=int, default=60, help="left/right safe-area margin (px)")
    ap.add_argument("--max-words", type=int, default=4)
    ap.add_argument("--uppercase", action="store_true")
    ap.add_argument("--burn", action="store_true")
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--video-out")
    args = ap.parse_args()

    # drop standalone punctuation tokens WhisperX sometimes emits (else they render as stray ","/".")
    words = [w for w in json.load(open(args.transcript)).get("words", [])
             if any(c.isalnum() for c in w.get("word", ""))]
    ass = build(words, args.play_w, args.play_h, args.y, args.font_size, args.max_words,
                args.uppercase, args.margin, args.font_min)
    Path(args.out).write_text(ass)
    print(json.dumps({"event": "ass_written", "cues": ass.count("Dialogue:"), "out": args.out}))

    if args.burn:
        if not (args.inp and args.video_out):
            print("ERROR: --burn needs --in and --video-out", file=sys.stderr); return 2
        esc_ass = args.out.replace(":", "\\:")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", args.inp, "-vf", f"subtitles={esc_ass}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "copy", "-movflags", "+faststart", args.video_out],
            capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr[-1500:], file=sys.stderr); return 3
        print(json.dumps({"event": "burned", "out": args.video_out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
