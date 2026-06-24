#!/usr/bin/env python3
"""Burn phrase-level blue caption overlays onto the locally rendered Shorts."""

from __future__ import annotations

import os
import json
import math
import re
import shlex
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(os.environ.get("EDDY_YT_TOOLS_ROOT", "~/YouTube")).expanduser()
PY_ROOT = Path(os.environ.get("EDDY_YT_TOOLS_PY_ROOT", "~/.cache/codex-runtimes/codex-primary-runtime/dependencies")).expanduser()
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
TRANSCRIPT = ROOT / "source/edit/transcript.faster-whisper.json"
OUT_DIR = ROOT / "source/exports/shorts"
CAPTION_DIR = OUT_DIR / "caption_assets"

SHORTS = [
    {
        "slug": "proof-beats-subscribers",
        "source": OUT_DIR / "proof-beats-subscribers.mp4",
        "segments": [(959.35, 1033.17)],
    },
    {
        "slug": "clients-hunt-you",
        "source": OUT_DIR / "clients-hunt-you.mp4",
        "segments": [(1329.40, 1421.01)],
    },
    {
        "slug": "show-systems-not-pitches",
        "source": OUT_DIR / "show-systems-not-pitches.mp4",
        "segments": [(1646.97, 1737.20)],
    },
    {
        "slug": "your-weird-skill-stack",
        "source": OUT_DIR / "your-weird-skill-stack.mp4",
        "segments": [(2119.92, 2209.06)],
    },
    {
        "slug": "do-free-work-strategically",
        "source": OUT_DIR / "do-free-work-strategically.mp4",
        "segments": [(2653.72, 2711.88), (2793.28, 2818.07)],
    },
    {
        "slug": "let-them-name-price",
        "source": OUT_DIR / "let-them-name-price.mp4",
        "segments": [(3149.28, 3154.02), (3230.95, 3250.85), (3259.69, 3304.47)],
    },
    {
        "slug": "do-not-sign-first-contract",
        "source": OUT_DIR / "do-not-sign-first-contract.mp4",
        "segments": [(3504.60, 3567.16), (3615.39, 3628.38)],
    },
    {
        "slug": "small-audience-real-client",
        "source": OUT_DIR / "small-audience-real-client.mp4",
        "segments": [
            (280.893, 287.946),
            (299.760, 308.821),
            (313.656, 319.811),
            (323.922, 324.128),
            (324.879, 325.100),
            (327.040, 329.811),
            (330.831, 332.484),
            (334.502, 337.000),
        ],
    },
    {
        "slug": "proof-in-twelve-seconds",
        "source": OUT_DIR / "proof-in-twelve-seconds.mp4",
        "segments": [
            (661.741, 662.078),
            (664.678, 682.950),
            (683.295, 686.626),
            (687.262, 697.060),
            (724.990, 727.571),
            (728.814, 737.080),
        ],
    },
    {
        "slug": "ask-the-win-question",
        "source": OUT_DIR / "ask-the-win-question.mp4",
        "segments": [
            (1990.000, 1996.487),
            (2004.254, 2010.431),
            (2019.485, 2023.545),
            (2026.997, 2037.100),
            (2049.862, 2061.960),
        ],
    },
    {
        "slug": "one-skill-is-common",
        "source": OUT_DIR / "one-skill-is-common.mp4",
        "segments": [
            (2288.000, 2291.084),
            (2291.678, 2298.289),
            (2299.226, 2302.122),
            (2308.118, 2310.784),
            (2311.694, 2318.657),
            (2319.532, 2330.903),
            (2331.731, 2336.578),
            (2351.450, 2351.653),
            (2379.011, 2384.093),
            (2385.094, 2389.207),
            (2390.256, 2391.000),
        ],
    },
    {
        "slug": "bounded-first-phase",
        "source": OUT_DIR / "bounded-first-phase.mp4",
        "segments": [
            (3293.000, 3297.471),
            (3298.072, 3302.097),
            (3304.107, 3310.450),
            (3312.700, 3316.333),
            (3317.155, 3317.973),
            (3324.387, 3329.357),
            (3330.230, 3336.398),
            (3337.668, 3340.486),
            (3340.861, 3342.710),
        ],
    },
    {
        "slug": "random-mix-is-valuable",
        "source": OUT_DIR / "random-mix-is-valuable.mp4",
        "segments": [
            (3912.880, 3916.616),
            (3918.637, 3920.314),
            (3922.563, 3926.763),
            (3946.681, 3949.766),
            (3951.410, 3955.773),
            (3958.531, 3967.352),
            (3968.782, 3970.540),
            (3970.909, 3982.000),
        ],
    },
    {
        "slug": "make-proof-this-week",
        "source": OUT_DIR / "make-proof-this-week.mp4",
        "segments": [
            (3999.867, 4011.572),
            (4012.495, 4015.148),
            (4016.944, 4022.966),
            (4024.409, 4033.759),
            (4034.230, 4035.160),
        ],
    },
    {
        "slug": "share-your-losses",
        "source": OUT_DIR / "share-your-losses.mp4",
        "segments": [
            (4136.010, 4140.140),
            (4141.029, 4150.909),
            (4151.529, 4153.761),
            (4154.191, 4154.438),
            (4159.166, 4163.274),
            (4164.435, 4165.586),
            (4166.182, 4176.231),
            (4179.134, 4191.650),
        ],
    },
]


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


FONT = load_font(54)
SMALL_FONT = load_font(48)


def clean_word(word: str) -> str:
    return word.strip().replace("’", "'")


def is_marker_phrase(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return normalized in {"hook for short", "hook four short", "book for short", "book4short"}


def transcript_words() -> list[dict[str, float | str]]:
    data = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
    words: list[dict[str, float | str]] = []
    for segment in data["segments"]:
        for word in segment.get("words", []):
            text = clean_word(word["word"])
            if text:
                words.append({"start": float(word["start"]), "end": float(word["end"]), "word": text})
    return words


def raw_to_output_time(raw_time: float, segments: list[tuple[float, float]]) -> float | None:
    elapsed = 0.0
    for start, end in segments:
        if start <= raw_time <= end:
            return elapsed + raw_time - start
        elapsed += end - start
    return None


def cue_words(words: list[dict[str, float | str]], segments: list[tuple[float, float]]) -> list[dict[str, object]]:
    selected: list[dict[str, float | str]] = []
    for word in words:
        start = float(word["start"])
        end = float(word["end"])
        out_start = raw_to_output_time(start, segments)
        out_end = raw_to_output_time(end, segments)
        if out_start is None or out_end is None:
            continue
        selected.append({"start": out_start, "end": out_end, "word": str(word["word"])})

    cues: list[dict[str, object]] = []
    current: list[dict[str, float | str]] = []
    cue_start = 0.0
    for word in selected:
        if not current:
            cue_start = float(word["start"])
        current.append(word)
        text = " ".join(str(item["word"]) for item in current)
        duration = float(word["end"]) - cue_start
        if len(current) >= 5 or duration >= 1.55 or len(text) >= 38:
            if not is_marker_phrase(text):
                cues.append({"start": cue_start, "end": float(word["end"]) + 0.12, "words": current[:]})
            current.clear()
    if current:
        text = " ".join(str(item["word"]) for item in current)
        if not is_marker_phrase(text):
            cues.append({"start": cue_start, "end": float(current[-1]["end"]) + 0.12, "words": current[:]})
    return cues


def wrap_words(words: list[str], font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current: list[str] = []
    probe = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(probe)
    for word in words:
        trial = " ".join([*current, word]).upper()
        width = draw.textbbox((0, 0), trial, font=font, stroke_width=3)[2]
        if current and width > max_width:
            lines.append(" ".join(current).upper())
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current).upper())
    return lines[:2]


def render_caption(path: Path, text: str) -> None:
    image = Image.new("RGBA", (1080, 220), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    words = text.split()
    font = FONT
    lines = wrap_words(words, font, 900)
    if len(lines) > 1 and max(draw.textbbox((0, 0), line, font=font, stroke_width=3)[2] for line in lines) > 920:
        font = SMALL_FONT
        lines = wrap_words(words, font, 900)

    line_height = font.size + 12
    block_height = len(lines) * line_height
    y = math.floor((220 - block_height) / 2)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=4)
        x = math.floor((1080 - (bbox[2] - bbox[0])) / 2)
        draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0, 180), stroke_width=4, stroke_fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=font, fill=(44, 160, 255, 255), stroke_width=4, stroke_fill=(3, 10, 22, 255))
        y += line_height
    image.save(path)


def ffmpeg_escape(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:")


def burn_short(short: dict[str, object], words: list[dict[str, float | str]]) -> Path:
    slug = str(short["slug"])
    source = Path(short["source"])
    segments = short["segments"]  # type: ignore[assignment]
    cue_list = cue_words(words, segments)  # type: ignore[arg-type]
    asset_dir = CAPTION_DIR / slug
    asset_dir.mkdir(parents=True, exist_ok=True)

    inputs = ["-i", str(source)]
    for idx, cue in enumerate(cue_list):
        text = " ".join(str(item["word"]) for item in cue["words"])  # type: ignore[index]
        caption_path = asset_dir / f"caption-{idx:03d}.png"
        render_caption(caption_path, text)
        inputs.extend(["-loop", "1", "-i", str(caption_path)])

    filters = []
    last = "[0:v]"
    for idx, cue in enumerate(cue_list, start=1):
        out = f"[v{idx}]"
        enable = f"between(t\\,{float(cue['start']):.3f}\\,{float(cue['end']):.3f})"
        filters.append(f"{last}[{idx}:v]overlay=0:1690:enable='{enable}'{out}")
        last = out

    target = OUT_DIR / f"{slug}-captioned.mp4"
    cmd = [
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
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(target),
    ]
    print(f"{slug}: {len(cue_list)} caption cues")
    print(shlex.join(cmd[:12]) + " ...")
    subprocess.run(cmd, check=True)
    return target


def main() -> None:
    words = transcript_words()
    outputs = [str(burn_short(short, words)) for short in SHORTS]
    (OUT_DIR / "captioned-outputs.txt").write_text("\n".join(outputs) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
