#!/usr/bin/env python3
"""Render the approval sample for the redesigned Shorts layout."""

from __future__ import annotations

import os
import argparse
import json
import math
import re
import shlex
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(os.environ.get("EDDY_YT_TOOLS_ROOT", "~/YouTube")).expanduser()
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
CAMERA = ROOT / "source/raw/camera.mp4"
SCREEN = ROOT / "source/raw/screen.mp4"
TRANSCRIPT = ROOT / "source/edit/transcript.faster-whisper.json"
OUT_ROOT = ROOT / "source/exports/shorts-redesign-sample"

SHORTS = {
    "clients-hunt-you": {
        "title": "Clients Hunt You",
        "segments": [(1329.40, 1421.01)],
    },
    "clients-hunt-you-v2": {
        "title": "Clients Hunt You V2",
        "segments": [
            (1328.60, 1336.20),
            (1384.94, 1421.01),
        ],
    },
    "clients-hunt-you-v3": {
        "title": "Clients Hunt You V3",
        "segments": [
            (1328.68, 1335.40),
            (1340.40, 1342.22),
            (1384.66, 1387.08),
            (1387.32, 1391.04),
            (1400.34, 1404.18),
            (1404.34, 1407.82),
            (1410.52, 1412.50),
            (1412.82, 1415.00),
            (1419.90, 1421.08),
        ],
    }
}

W, H = 1080, 1920
BG = "0x07111f"
FACE_SIZE = 900
FACE_X = (W - FACE_SIZE) // 2
FACE_Y = 34
CAPTION_Y = 944
CAPTION_H = 250
SCREEN_W = 1000
SCREEN_H = 562
SCREEN_X = (W - SCREEN_W) // 2
SCREEN_Y = 1254
RADIUS = 34


def run(cmd: list[str]) -> None:
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True)


def ass_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
    )


def filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    c = cs % 100
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def clean_word(word: str) -> str:
    word = re.sub(r"\s+", " ", word.strip().replace("’", "'"))
    return re.sub(r"^[^A-Za-z0-9']+|[^A-Za-z0-9']+$", "", word)


def transcript_words() -> list[dict[str, float | str]]:
    data = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
    words: list[dict[str, float | str]] = []
    for segment in data["segments"]:
        for word in segment.get("words", []):
            text = clean_word(word["word"])
            if not text:
                continue
            start = float(word["start"])
            end = float(word["end"])
            if end <= start:
                end = start + 0.16
            words.append({"start": start, "end": end, "word": text})
    return words


def raw_to_output_time(raw_time: float, segments: list[tuple[float, float]]) -> float | None:
    elapsed = 0.0
    for start, end in segments:
        if start <= raw_time <= end:
            return elapsed + raw_time - start
        elapsed += end - start
    return None


def selected_words(segments: list[tuple[float, float]]) -> list[dict[str, float | str]]:
    selected: list[dict[str, float | str]] = []
    for word in transcript_words():
        raw_start = float(word["start"])
        raw_end = float(word["end"])
        start = raw_to_output_time(raw_start, segments)
        end = raw_to_output_time(raw_end, segments)
        if start is None or end is None:
            continue
        selected.append({"start": start, "end": max(end, start + 0.14), "word": str(word["word"])})
    return selected


def load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default(size=size)


def word_width(word: str, font: ImageFont.FreeTypeFont) -> int:
    probe = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), word.upper(), font=font, stroke_width=2)
    return bbox[2] - bbox[0]


def group_cues(words: list[dict[str, float | str]]) -> list[list[dict[str, float | str]]]:
    font = load_font(55)
    cues: list[list[dict[str, float | str]]] = []
    current: list[dict[str, float | str]] = []
    width = 0
    for word in words:
        text = str(word["word"])
        next_width = width + word_width(text, font) + (24 if current else 0)
        duration = float(word["end"]) - float(current[0]["start"]) if current else 0.0
        if current and (len(current) >= 6 or duration >= 2.0 or next_width > 930):
            cues.append(current)
            current = []
            width = 0
        current.append(word)
        width += word_width(text, font) + (24 if len(current) > 1 else 0)
    if current:
        cues.append(current)
    return cues


def word_markup(words: list[dict[str, float | str]], current_idx: int) -> str:
    rendered: list[str] = []
    for idx, word in enumerate(words):
        text = ass_escape(str(word["word"]).upper())
        if idx < current_idx:
            rendered.append(r"{\c&HFFFFFF&\bord3}" + text)
        elif idx == current_idx:
            rendered.append(r"{\c&H2DA8FF&\bord5\3c&H00101F&}" + text)
        else:
            rendered.append(r"{\c&H6C7A88&\alpha&H35&\bord3}" + text)
    return " ".join(rendered)


def render_caption_png(path: Path, cue: list[dict[str, float | str]], current_idx: int) -> None:
    font = load_font(55)
    small_font = load_font(48)
    words = [str(word["word"]).upper() for word in cue]
    widths = [word_width(word, font) for word in words]
    gap = 22
    total_width = sum(widths) + gap * (len(words) - 1)
    if total_width > 960:
        font = small_font
        widths = [word_width(word, font) for word in words]
        gap = 18
        total_width = sum(widths) + gap * (len(words) - 1)

    image = Image.new("RGBA", (W, CAPTION_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x = math.floor((W - total_width) / 2)
    y = 76 if font.size >= 55 else 82
    for idx, word in enumerate(words):
        width = widths[idx]
        if idx == current_idx:
            draw.rounded_rectangle(
                (x - 16, y - 12, x + width + 16, y + font.size + 18),
                radius=20,
                fill=(20, 118, 205, 220),
            )
            fill = (255, 255, 255, 255)
            stroke = (1, 10, 22, 230)
            stroke_width = 3
        elif idx < current_idx:
            fill = (245, 250, 255, 255)
            stroke = (1, 10, 22, 230)
            stroke_width = 3
        else:
            fill = (132, 145, 160, 125)
            stroke = (1, 10, 22, 120)
            stroke_width = 2
        draw.text((x, y), word, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke)
        x += width + gap
    image.save(path)


def caption_events(asset_dir: Path, segments: list[tuple[float, float]]) -> list[dict[str, float | Path]]:
    cue_dir = asset_dir / "caption-states"
    cue_dir.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, float | Path]] = []
    previous_global_end = 0.0
    for cue_idx, cue in enumerate(group_cues(selected_words(segments))):
        for word_idx, word in enumerate(cue):
            start = max(float(word["start"]), previous_global_end)
            next_start = float(cue[word_idx + 1]["start"]) if word_idx + 1 < len(cue) else float(word["end"]) + 0.24
            end = max(next_start, start + 0.12)
            path = cue_dir / f"caption-{cue_idx:03d}-{word_idx:02d}.png"
            render_caption_png(path, cue, word_idx)
            events.append({"start": start, "end": end, "path": path})
            previous_global_end = end
    return events


def make_mask(path: Path, size: tuple[int, int], radius: int) -> None:
    image = Image.new("L", size, 0)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    image.save(path)


def filter_script(path: Path, segments: list[tuple[float, float]]) -> None:
    parts: list[str] = []
    screen_labels: list[str] = []
    camera_labels: list[str] = []
    audio_labels: list[str] = []
    for idx, (start, end) in enumerate(segments):
        parts.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,"
            f"scale={SCREEN_W}:{SCREEN_H}:force_original_aspect_ratio=decrease,"
            f"pad={SCREEN_W}:{SCREEN_H}:(ow-iw)/2:(oh-ih)/2:color={BG},"
            f"setsar=1[sv{idx}]"
        )
        parts.append(
            f"[1:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,"
            f"crop=1080:1080:420:0,scale={FACE_SIZE}:{FACE_SIZE},setsar=1[cv{idx}]"
        )
        parts.append(f"[1:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{idx}]")
        screen_labels.append(f"[sv{idx}]")
        camera_labels.append(f"[cv{idx}]")
        audio_labels.append(f"[a{idx}]")
    n = len(segments)
    parts.append("".join(screen_labels) + f"concat=n={n}:v=1:a=0[sraw]")
    parts.append("".join(camera_labels) + f"concat=n={n}:v=1:a=0[craw]")
    parts.append("".join(audio_labels) + f"concat=n={n}:v=0:a=1[a]")
    parts.append("[sraw]format=rgba[srgba]")
    parts.append("[craw]format=rgba[crgba]")
    parts.append("[srgba][2:v]alphamerge[sround]")
    parts.append("[crgba][3:v]alphamerge[cround]")
    total_duration = sum(end - start for start, end in segments)
    parts.append(f"color=c={BG}:s={W}x{H}:d={total_duration:.3f},format=rgba[base]")
    parts.append(f"[base][cround]overlay={FACE_X}:{FACE_Y}:format=auto[tmp]")
    parts.append(f"[tmp][sround]overlay={SCREEN_X}:{SCREEN_Y}:format=auto[v]")
    path.write_text(";\n".join(parts), encoding="utf-8")


def render_sample(slug: str) -> Path:
    short = SHORTS[slug]
    out_dir = OUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    face_mask = out_dir / "face-mask.png"
    screen_mask = out_dir / "screen-mask.png"
    base_filter = out_dir / "layout.filter.txt"
    base = out_dir / f"{slug}-redesign-base.mp4"
    final = out_dir / f"{slug}-redesign-sample.mp4"

    segments = short["segments"]
    make_mask(face_mask, (FACE_SIZE, FACE_SIZE), RADIUS)
    make_mask(screen_mask, (SCREEN_W, SCREEN_H), RADIUS)
    filter_script(base_filter, segments)

    if not base.exists():
        run(
            [
                FFMPEG,
                "-y",
                "-hide_banner",
                "-i",
                str(SCREEN),
                "-i",
                str(CAMERA),
                "-i",
                str(screen_mask),
                "-i",
                str(face_mask),
                "-filter_complex_script",
                str(base_filter),
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "h264_videotoolbox",
                "-allow_sw",
                "1",
                "-b:v",
                "7500k",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(base),
            ]
        )
    events = caption_events(out_dir, segments)
    burn_captions(base, final, events)
    make_contact_sheet(final, out_dir, events)
    return final


def burn_captions(base: Path, final: Path, events: list[dict[str, float | Path]]) -> None:
    inputs: list[str] = ["-i", str(base)]
    for event in events:
        inputs.extend(["-loop", "1", "-i", str(event["path"])])

    filters: list[str] = []
    last = "[0:v]"
    for idx, event in enumerate(events, start=1):
        out = f"[v{idx}]"
        enable = f"between(t\\,{float(event['start']):.3f}\\,{float(event['end']):.3f})"
        filters.append(f"{last}[{idx}:v]overlay=0:{CAPTION_Y}:enable='{enable}'{out}")
        last = out

    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            last,
            "-map",
            "0:a",
            "-c:v",
            "h264_videotoolbox",
            "-allow_sw",
            "1",
            "-b:v",
            "7500k",
            "-c:a",
            "copy",
            "-shortest",
            "-movflags",
            "+faststart",
            str(final),
        ]
    )


def duration(path: Path) -> float:
    output = subprocess.check_output(
        [
            FFMPEG.replace("ffmpeg", "ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    )
    return float(output.strip())


def make_contact_sheet(video: Path, out_dir: Path, events: list[dict[str, float | Path]] | None = None) -> None:
    dur = duration(video)
    if events and len(events) >= 3:
        sample_events = [events[2], events[len(events) // 2], events[-3]]
        stamps = [
            (float(event["start"]) + float(event["end"])) / 2
            for event in sample_events
        ]
    else:
        stamps = [max(1.0, dur * 0.15), dur * 0.5, max(1.0, dur * 0.85)]
    frames: list[Path] = []
    for idx, stamp in enumerate(stamps, start=1):
        frame = out_dir / f"qa-frame-{idx:02d}.jpg"
        run(
            [
                FFMPEG,
                "-y",
                "-hide_banner",
                "-ss",
                f"{stamp:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame),
            ]
        )
        frames.append(frame)
    contact = out_dir / "qa-contact-sheet.jpg"
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            *sum((["-i", str(frame)] for frame in frames), []),
            "-filter_complex",
            "[0:v]scale=360:-1[a];[1:v]scale=360:-1[b];[2:v]scale=360:-1[c];[a][b][c]hstack=inputs=3[v]",
            "-map",
            "[v]",
            "-q:v",
            "2",
            str(contact),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", choices=sorted(SHORTS), default="clients-hunt-you")
    args = parser.parse_args()
    final = render_sample(args.sample)
    print(f"sample={final}")


if __name__ == "__main__":
    main()
