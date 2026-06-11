#!/usr/bin/env python3
"""Render approved redesigned Shorts from raw camera/screen plus transcript timings."""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/Users/yassybabes/YouTube")
FFMPEG = "/Users/yassybabes/.homebrew/bin/ffmpeg"
FFPROBE = FFMPEG.replace("ffmpeg", "ffprobe")
CAMERA = ROOT / "source/raw/camera.mp4"
SCREEN = ROOT / "source/raw/screen.mp4"
TRANSCRIPT = ROOT / "source/edit/transcript.faster-whisper.json"
LOCAL_SHORTS = ROOT / "tools/render_local_shorts.py"
OUT_ROOT = ROOT / "source/exports/shorts-redesign-approved"

APPROVED_SAMPLE_SLUG = "clients-hunt-you"
EXCLUDED_SHORT_SLUGS = {"do-not-sign-first-contract"}

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
GAP_CUT_THRESHOLD = 0.68
START_HANDLE = 0.24
INTERNAL_END_HANDLE = 0.32
FINAL_END_HANDLE = 0.52
MANUAL_GAP_SPLIT_THRESHOLD = 0.68
EDGE_EXTENSION = 0.50
GLUED_WORD_GAP = 0.08
MAX_EDGE_WORD_EXPANSION = 3

MARKERS = (
    ("hook", "for", "short"),
    ("hook", "four", "short"),
    ("book", "for", "short"),
    ("book4short",),
)

MANUAL_SEGMENT_OVERRIDES = {
    "ask-the-win-question": [
        (1989.32, 1996.42),
        (2004.04, 2010.32),
        (2028.45, 2037.11),
        (2049.74, 2061.96),
    ],
    "bounded-first-phase": [
        (3293.06, 3301.84),
        (3301.84, 3302.92),
        (3304.29, 3310.27),
        (3312.91, 3316.40),
        (3316.77, 3318.02),
        (3324.09, 3329.23),
        (3330.02, 3336.32),
        (3337.50, 3342.95),
    ],
    "do-free-work-strategically": [
        (2652.76, 2656.36),
        (2668.97, 2671.17),
        (2675.53, 2677.93),
        (2686.80, 2694.16),
        (2701.48, 2714.20),
        (2791.56, 2801.10),
        (2803.70, 2808.24),
    ],
    "do-not-sign-first-contract": [
        (3504.52, 3510.00),
        (3527.58, 3530.30),
        (3531.08, 3532.26),
        (3553.10, 3557.84),
        (3559.71, 3564.32),
        (3566.34, 3567.26),
        (3618.35, 3624.05),
        (3625.16, 3626.60),
        (3627.10, 3628.38),
    ],
    "let-them-name-price": [
        (3149.20, 3154.12),
        (3230.87, 3239.95),
        (3247.37, 3250.95),
        (3259.61, 3262.91),
        (3267.94, 3272.14),
        (3274.30, 3275.62),
        (3282.95, 3288.03),
        (3288.69, 3297.30),
        (3297.78, 3317.90),
    ],
    "make-proof-this-week": [
        (3999.78, 4011.48),
        (4016.68, 4022.74),
        (4024.12, 4035.16),
    ],
    "one-skill-is-common": [
        (2285.99, 2293.08),
        (2293.27, 2297.07),
        (2299.45, 2301.45),
        (2311.18, 2318.66),
        (2319.15, 2331.00),
        (2331.50, 2336.58),
        (2378.91, 2384.30),
        (2385.00, 2389.20),
        (2390.20, 2410.80),
    ],
    "proof-beats-subscribers": [
        (980.15, 988.95),
        (1003.14, 1008.60),
        (1009.90, 1010.78),
        (1011.88, 1017.98),
        (1027.04, 1028.35),
        (1030.45, 1056.41),
        (1058.94, 1067.35),
    ],
    "proof-in-twelve-seconds": [
        (664.52, 682.30),
        (693.20, 697.16),
        (729.12, 737.08),
    ],
    "random-mix-is-valuable": [
        (3912.83, 3916.49),
        (3922.43, 3926.67),
        (3946.48, 3949.80),
        (3951.20, 3955.77),
        (3958.37, 3967.15),
        (3968.64, 3982.44),
    ],
    "share-your-losses": [
        (4135.82, 4140.10),
        (4141.00, 4150.64),
        (4151.34, 4153.76),
        (4158.99, 4163.40),
        (4164.35, 4165.43),
        (4166.17, 4174.57),
        (4184.79, 4191.65),
    ],
    "show-systems-not-pitches": [
        (1655.04, 1663.20),
        (1670.08, 1753.60),
    ],
    "small-audience-real-client": [
        (280.76, 287.94),
        (299.82, 308.82),
        (313.45, 319.81),
        (327.01, 331.97),
        (334.10, 337.54),
    ],
    "your-weird-skill-stack": [
        (2135.53, 2144.37),
        (2151.06, 2157.28),
        (2159.58, 2163.48),
        (2167.39, 2169.79),
        (2179.16, 2181.96),
    ],
}


def run(cmd: list[str]) -> None:
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True)


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def clean_word(word: str) -> str:
    word = re.sub(r"\s+", " ", word.strip().replace("’", "'"))
    return re.sub(r"^[^A-Za-z0-9']+|[^A-Za-z0-9']+$", "", word)


def norm_word(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", word.lower())


def load_source_shorts() -> list[dict[str, Any]]:
    tree = ast.parse(LOCAL_SHORTS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SHORTS":
                    return ast.literal_eval(node.value)
    raise RuntimeError(f"Could not find SHORTS in {LOCAL_SHORTS}")


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


def words_in_ranges(
    words: list[dict[str, float | str]], ranges: list[tuple[float, float]]
) -> list[dict[str, float | str]]:
    return [
        word
        for word in words
        if any(start <= float(word["start"]) <= end for start, end in ranges)
    ]


def remove_marker_words(words: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    normalized = [norm_word(str(word["word"])) for word in words]
    skip: set[int] = set()
    for idx in range(len(normalized)):
        for marker in MARKERS:
            if tuple(normalized[idx : idx + len(marker)]) == marker:
                skip.update(range(idx, idx + len(marker)))
    return [word for idx, word in enumerate(words) if idx not in skip]


def marker_indices(words: list[dict[str, float | str]]) -> set[int]:
    normalized = [norm_word(str(word["word"])) for word in words]
    skip: set[int] = set()
    for idx in range(len(normalized)):
        for marker in MARKERS:
            if tuple(normalized[idx : idx + len(marker)]) == marker:
                skip.update(range(idx, idx + len(marker)))
    return skip


def derive_phrase_segments(
    source_segments: list[tuple[float, float]], words: list[dict[str, float | str]]
) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    source_words = words_in_ranges(words, source_segments)
    kept_words = remove_marker_words(source_words)
    raw_duration = sum(end - start for start, end in source_segments)
    if not kept_words:
        return source_segments, {
            "raw_duration": raw_duration,
            "cleaned_duration": raw_duration,
            "removed_seconds": 0.0,
            "word_count": 0,
            "note": "no transcript words found; kept source segments",
        }

    chunks: list[list[dict[str, float | str]]] = []
    current: list[dict[str, float | str]] = []
    gaps_cut = 0
    for word in kept_words:
        if current and float(word["start"]) - float(current[-1]["end"]) > GAP_CUT_THRESHOLD:
            chunks.append(current)
            current = []
            gaps_cut += 1
        current.append(word)
    if current:
        chunks.append(current)

    min_start = min(start for start, _ in source_segments)
    max_end = max(end for _, end in source_segments)
    segments: list[tuple[float, float]] = []
    for idx, chunk in enumerate(chunks):
        final_chunk = idx == len(chunks) - 1
        expanded_chunk = expand_glued_edge_words(words, chunk, min_start, max_end)
        start_floor = max(0.0, min(min_start, float(expanded_chunk[0]["start"])) - EDGE_EXTENSION)
        end_ceiling = max(max_end, float(expanded_chunk[-1]["end"])) + EDGE_EXTENSION
        start = safe_segment_start(words, expanded_chunk[0], start_floor)
        end = safe_segment_end(words, expanded_chunk[-1], end_ceiling, final_chunk)
        if end - start >= 0.22:
            segments.append((round(start, 3), round(end, 3)))

    merged: list[tuple[float, float]] = []
    for start, end in segments:
        if merged and start - merged[-1][1] < 0.16:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    cleaned_duration = sum(end - start for start, end in merged)
    return merged, {
        "raw_duration": round(raw_duration, 3),
        "cleaned_duration": round(cleaned_duration, 3),
        "removed_seconds": round(raw_duration - cleaned_duration, 3),
        "word_count": len(kept_words),
        "gaps_cut": gaps_cut,
        "first_words": " ".join(str(word["word"]) for word in kept_words[:18]),
    }


def words_inside_range(
    words: list[dict[str, float | str]], start: float, end: float
) -> list[dict[str, float | str]]:
    return [
        word
        for word in words
        if start <= float(word["start"]) and float(word["end"]) <= end
    ]


def word_index(words: list[dict[str, float | str]], target: dict[str, float | str]) -> int:
    target_start = float(target["start"])
    target_end = float(target["end"])
    target_text = str(target["word"])
    for idx, word in enumerate(words):
        if (
            abs(float(word["start"]) - target_start) < 0.001
            and abs(float(word["end"]) - target_end) < 0.001
            and str(word["word"]) == target_text
        ):
            return idx
    raise ValueError(f"Could not locate word in transcript: {target_text} {target_start}-{target_end}")


def expand_glued_edge_words(
    words: list[dict[str, float | str]],
    chunk_words: list[dict[str, float | str]],
    source_start: float,
    source_end: float,
) -> list[dict[str, float | str]]:
    """Include adjacent words when a requested boundary has no real audio gap."""
    if not chunk_words:
        return chunk_words

    start_idx = word_index(words, chunk_words[0])
    end_idx = word_index(words, chunk_words[-1])
    marker_skip = marker_indices(words)

    expansions = 0
    while start_idx > 0 and expansions < MAX_EDGE_WORD_EXPANSION:
        if start_idx - 1 in marker_skip:
            break
        previous_word = words[start_idx - 1]
        current_word = words[start_idx]
        gap = float(current_word["start"]) - float(previous_word["end"])
        if gap > GLUED_WORD_GAP or float(previous_word["end"]) < source_start - EDGE_EXTENSION:
            break
        start_idx -= 1
        expansions += 1

    expansions = 0
    while end_idx + 1 < len(words) and expansions < MAX_EDGE_WORD_EXPANSION:
        if end_idx + 1 in marker_skip:
            break
        current_word = words[end_idx]
        next_word = words[end_idx + 1]
        gap = float(next_word["start"]) - float(current_word["end"])
        if gap > GLUED_WORD_GAP or float(next_word["start"]) > source_end + EDGE_EXTENSION:
            break
        end_idx += 1
        expansions += 1

    return words[start_idx : end_idx + 1]


def safe_segment_start(
    words: list[dict[str, float | str]], first_word: dict[str, float | str], floor: float
) -> float:
    first_start = float(first_word["start"])
    desired = max(first_start - START_HANDLE, floor)
    previous_words = [word for word in words if float(word["end"]) <= first_start]
    if not previous_words:
        return desired
    previous_end = float(previous_words[-1]["end"])
    if previous_end > desired:
        gap = first_start - previous_end
        if gap >= 0.10:
            return max(previous_end + min(0.02, gap / 5), floor)
        return max(first_start - 0.04, floor)
    return desired


def safe_segment_end(
    words: list[dict[str, float | str]],
    last_word: dict[str, float | str],
    ceiling: float | None,
    final_chunk: bool,
) -> float:
    last_end = float(last_word["end"])
    handle = FINAL_END_HANDLE if final_chunk else INTERNAL_END_HANDLE
    desired = last_end + handle
    next_words = [word for word in words if float(word["start"]) >= last_end]
    if next_words and float(next_words[0]["start"]) <= desired + 0.02:
        next_start = float(next_words[0]["start"])
        keepaway = 0.14 if final_chunk else 0.05
        desired = max(last_end + 0.12, next_start - keepaway)
    if ceiling is not None and not final_chunk:
        desired = min(desired, ceiling)
    return desired


def polish_manual_segments(
    manual_segments: list[tuple[float, float]], words: list[dict[str, float | str]]
) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    polished: list[tuple[float, float]] = []
    gaps_cut = 0
    kept_word_count = 0

    for segment_idx, (source_start, source_end) in enumerate(manual_segments):
        range_words = remove_marker_words(words_inside_range(words, source_start, source_end))
        if not range_words:
            polished.append((source_start, source_end))
            continue

        chunk: list[dict[str, float | str]] = []
        chunks: list[list[dict[str, float | str]]] = []
        for word in range_words:
            if chunk and float(word["start"]) - float(chunk[-1]["end"]) > MANUAL_GAP_SPLIT_THRESHOLD:
                chunks.append(chunk)
                chunk = []
                gaps_cut += 1
            chunk.append(word)
        if chunk:
            chunks.append(chunk)

        kept_word_count += len(range_words)
        for chunk_idx, chunk_words in enumerate(chunks):
            final_chunk = segment_idx == len(manual_segments) - 1 and chunk_idx == len(chunks) - 1
            expanded_chunk = expand_glued_edge_words(words, chunk_words, source_start, source_end)
            start_floor = max(0.0, min(source_start, float(expanded_chunk[0]["start"])) - EDGE_EXTENSION)
            end_ceiling = max(source_end, float(expanded_chunk[-1]["end"])) + EDGE_EXTENSION
            start = safe_segment_start(words, expanded_chunk[0], start_floor)
            end = safe_segment_end(words, expanded_chunk[-1], end_ceiling, final_chunk)
            if end - start >= 0.22:
                polished.append((round(start, 3), round(end, 3)))

    merged: list[tuple[float, float]] = []
    for start, end in polished:
        if merged and start - merged[-1][1] < 0.08:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    raw_duration = sum(end - start for start, end in manual_segments)
    cleaned_duration = sum(end - start for start, end in merged)
    return merged, {
        "raw_duration": round(raw_duration, 3),
        "cleaned_duration": round(cleaned_duration, 3),
        "removed_seconds": round(raw_duration - cleaned_duration, 3),
        "word_count": kept_word_count,
        "gaps_cut": gaps_cut + max(0, len(merged) - len(manual_segments)),
        "first_words": "manual override polished against word timings with safe tails",
    }


def raw_to_output_time(raw_time: float, segments: list[tuple[float, float]]) -> float | None:
    elapsed = 0.0
    for start, end in segments:
        if start <= raw_time <= end:
            return elapsed + raw_time - start
        elapsed += end - start
    return None


def selected_words(
    words: list[dict[str, float | str]], segments: list[tuple[float, float]]
) -> list[dict[str, float | str]]:
    selected: list[dict[str, float | str]] = []
    for word in words:
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


def caption_events(
    asset_dir: Path, words: list[dict[str, float | str]], segments: list[tuple[float, float]]
) -> list[dict[str, float | Path]]:
    cue_dir = asset_dir / "caption-states"
    cue_dir.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, float | Path]] = []
    previous_global_end = 0.0
    for cue_idx, cue in enumerate(group_cues(selected_words(words, segments))):
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


def shell_quote_for_concat(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def render_layout_segment(
    out_dir: Path,
    index: int,
    start: float,
    end: float,
    screen_mask: Path,
    face_mask: Path,
) -> Path:
    duration_seconds = end - start
    segment = out_dir / "layout-segments" / f"segment-{index:03d}.mp4"
    segment.parent.mkdir(parents=True, exist_ok=True)
    filter_graph = (
        f"[0:v]scale={SCREEN_W}:{SCREEN_H}:force_original_aspect_ratio=decrease,"
        f"pad={SCREEN_W}:{SCREEN_H}:(ow-iw)/2:(oh-ih)/2:color={BG},setsar=1[sraw];"
        f"[1:v]crop=1080:1080:420:0,scale={FACE_SIZE}:{FACE_SIZE},setsar=1[craw];"
        "[sraw]format=rgba[srgba];[craw]format=rgba[crgba];"
        "[srgba][2:v]alphamerge[sround];[crgba][3:v]alphamerge[cround];"
        f"color=c={BG}:s={W}x{H}:d={duration_seconds:.3f},format=rgba[base];"
        f"[base][cround]overlay={FACE_X}:{FACE_Y}:format=auto[tmp];"
        f"[tmp][sround]overlay={SCREEN_X}:{SCREEN_Y}:format=auto[v];"
        "[1:a]asetpts=PTS-STARTPTS[a]"
    )
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration_seconds:.3f}",
            "-i",
            str(SCREEN),
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration_seconds:.3f}",
            "-i",
            str(CAMERA),
            "-i",
            str(screen_mask),
            "-i",
            str(face_mask),
            "-filter_complex",
            filter_graph,
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
            "-r",
            "25",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(segment),
        ]
    )
    return segment


def concat_layout_segments(out_dir: Path, segments: list[Path], base: Path) -> None:
    concat_file = out_dir / "layout-segments.ffconcat"
    concat_file.write_text(
        "ffconcat version 1.0\n"
        + "".join(f"file '{shell_quote_for_concat(segment)}'\n" for segment in segments),
        encoding="utf-8",
    )
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(base),
        ]
    )


def make_blank_caption(path: Path) -> None:
    Image.new("RGBA", (W, CAPTION_H), (0, 0, 0, 0)).save(path)


def make_caption_layer(
    out_dir: Path, events: list[dict[str, float | Path]], total_duration: float
) -> Path:
    blank = out_dir / "caption-blank.png"
    make_blank_caption(blank)
    concat_file = out_dir / "captions.ffconcat"
    layer = out_dir / "captions.mov"
    lines = ["ffconcat version 1.0"]
    cursor = 0.0
    for event in events:
        start = float(event["start"])
        end = float(event["end"])
        if start > cursor + 0.01:
            lines.append(f"file '{shell_quote_for_concat(blank)}'")
            lines.append(f"duration {start - cursor:.3f}")
        lines.append(f"file '{shell_quote_for_concat(Path(event['path']))}'")
        lines.append(f"duration {max(0.04, end - start):.3f}")
        cursor = end
    if total_duration > cursor + 0.01:
        lines.append(f"file '{shell_quote_for_concat(blank)}'")
        lines.append(f"duration {total_duration - cursor:.3f}")
    lines.append(f"file '{shell_quote_for_concat(blank)}'")
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-vf",
            "fps=25,format=argb",
            "-c:v",
            "qtrle",
            str(layer),
        ]
    )
    return layer


def burn_captions(
    base: Path, final: Path, events: list[dict[str, float | Path]], total_duration: float, out_dir: Path
) -> None:
    caption_layer = make_caption_layer(out_dir, events, total_duration)
    untrimmed = final.with_name(final.stem + "-untrimmed.mp4")
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-i",
            str(base),
            "-i",
            str(caption_layer),
            "-filter_complex",
            f"[0:v][1:v]overlay=0:{CAPTION_Y}:format=auto[v]",
            "-map",
            "[v]",
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
            "-t",
            f"{total_duration:.3f}",
            str(untrimmed),
        ]
    )
    trim_rendered_edges(untrimmed, final)


def leading_silence_end(video: Path) -> float:
    result = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-af",
            "silencedetect=noise=-35dB:d=0.08",
            "-f",
            "null",
            "-",
        ],
        text=True,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        check=False,
    )
    saw_start = False
    for line in result.stderr.splitlines():
        if "silence_start: 0" in line:
            saw_start = True
        if saw_start and "silence_end:" in line:
            match = re.search(r"silence_end: ([0-9.]+)", line)
            if match:
                return float(match.group(1))
    return 0.0


def trim_rendered_edges(source: Path, final: Path) -> None:
    trim_start = max(0.0, leading_silence_end(source) - 0.12)
    if trim_start <= 0.08:
        source.replace(final)
        return
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-ss",
            f"{trim_start:.3f}",
            "-i",
            str(source),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(final),
        ]
    )


def duration(path: Path) -> float:
    output = subprocess.check_output(
        [
            FFPROBE,
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


def make_contact_sheet(video: Path, out_dir: Path, events: list[dict[str, float | Path]]) -> Path:
    dur = duration(video)
    if len(events) >= 3:
        sample_events = [events[2], events[len(events) // 2], events[-3]]
        stamps = [(float(event["start"]) + float(event["end"])) / 2 for event in sample_events]
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
    return contact


def render_short(short: dict[str, Any], words: list[dict[str, float | str]], out_root: Path) -> dict[str, Any]:
    title = short["title"]
    slug = slugify(title)
    source_segments = [(float(start), float(end)) for start, end in short["segments"]]
    if slug in MANUAL_SEGMENT_OVERRIDES:
        segments, audit = polish_manual_segments(MANUAL_SEGMENT_OVERRIDES[slug], words)
    else:
        segments, audit = derive_phrase_segments(source_segments, words)
    out_dir = out_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    face_mask = out_dir / "face-mask.png"
    screen_mask = out_dir / "screen-mask.png"
    base = out_dir / f"{slug}-redesign-base.mp4"
    final = out_dir / f"{slug}-redesign-approved.mp4"
    segment_file = out_dir / "cleaned-segments.json"

    make_mask(face_mask, (FACE_SIZE, FACE_SIZE), RADIUS)
    make_mask(screen_mask, (SCREEN_W, SCREEN_H), RADIUS)
    segment_file.write_text(
        json.dumps(
            {
                "title": title,
                "slug": slug,
                "source_segments": source_segments,
                "cleaned_segments": segments,
                "audit": audit,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    layout_segments = [
        render_layout_segment(out_dir, idx, start, end, screen_mask, face_mask)
        for idx, (start, end) in enumerate(segments)
    ]
    concat_layout_segments(out_dir, layout_segments, base)
    events = caption_events(out_dir, words, segments)
    total_duration = sum(end - start for start, end in segments)
    burn_captions(base, final, events, total_duration, out_dir)
    contact = make_contact_sheet(final, out_dir, events)

    return {
        "title": title,
        "slug": slug,
        "duration": round(duration(final), 3),
        "output": str(final),
        "contact_sheet": str(contact),
        "cleaned_segments": str(segment_file),
        **audit,
    }


def write_batch_contact_sheet(entries: list[dict[str, Any]], out_root: Path) -> Path:
    contact_sheets = [Path(entry["contact_sheet"]) for entry in entries]
    batch = out_root / "qa-contact-sheet-all.jpg"
    inputs: list[str] = []
    tiles: list[str] = []
    for idx, sheet in enumerate(contact_sheets):
        inputs.extend(["-i", str(sheet)])
        tiles.append(f"[{idx}:v]scale=540:-1[t{idx}]")
    rows: list[str] = []
    for row_idx, start in enumerate(range(0, len(contact_sheets), 2)):
        pair = list(range(start, min(start + 2, len(contact_sheets))))
        if len(pair) == 2:
            tiles.append(f"[t{pair[0]}][t{pair[1]}]hstack=inputs=2[row{row_idx}]")
        else:
            tiles.append(f"[t{pair[0]}]pad=1080:ih:0:0:color={BG}[row{row_idx}]")
        rows.append(f"[row{row_idx}]")
    if len(rows) == 1:
        tiles.append(f"{rows[0]}copy[v]")
    else:
        tiles.append("".join(rows) + f"vstack=inputs={len(rows)}[v]")
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            *inputs,
            "-filter_complex",
            ";".join(tiles),
            "-map",
            "[v]",
            "-q:v",
            "2",
            str(batch),
        ]
    )
    return batch


def verify_entry(entry: dict[str, Any]) -> dict[str, Any]:
    output = Path(entry["output"])
    probe = subprocess.check_output(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=index,codec_type,width,height",
            "-of",
            "json",
            str(output),
        ],
        text=True,
    )
    subprocess.run([FFMPEG, "-v", "error", "-i", str(output), "-map", "0:a:0", "-f", "null", "-"], check=True)
    subprocess.run([FFMPEG, "-v", "error", "-i", str(output), "-map", "0:v:0", "-frames:v", "10", "-f", "null", "-"], check=True)
    return json.loads(probe)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--include-approved-sample", action="store_true")
    parser.add_argument("--slug", action="append", help="Render only a matching slug; can be repeated.")
    args = parser.parse_args()

    words = transcript_words()
    source_shorts = load_source_shorts()
    selected = []
    wanted = set(args.slug or [])
    for short in source_shorts:
        slug = slugify(short["title"])
        if slug == APPROVED_SAMPLE_SLUG and not args.include_approved_sample:
            continue
        if slug in EXCLUDED_SHORT_SLUGS:
            continue
        if wanted and slug not in wanted:
            continue
        selected.append(short)

    args.out_root.mkdir(parents=True, exist_ok=True)
    rendered_entries: list[dict[str, Any]] = []
    for short in selected:
        rendered_entries.append(render_short(short, words, args.out_root))

    for entry in rendered_entries:
        entry["ffprobe"] = verify_entry(entry)

    manifest_path = args.out_root / "render-manifest.json"
    if wanted and manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        by_slug = {entry["slug"]: entry for entry in existing}
        by_slug.update({entry["slug"]: entry for entry in rendered_entries})
        source_order = [
            slugify(short["title"])
            for short in source_shorts
            if slugify(short["title"]) != APPROVED_SAMPLE_SLUG
        ]
        manifest = [by_slug[slug] for slug in source_order if slug in by_slug]
    else:
        manifest = rendered_entries

    batch_contact = write_batch_contact_sheet(manifest, args.out_root)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (args.out_root / "captioned-outputs.txt").write_text(
        "\n".join(entry["output"] for entry in manifest) + "\n",
        encoding="utf-8",
    )
    print(f"rendered={len(manifest)}")
    print(f"manifest={args.out_root / 'render-manifest.json'}")
    print(f"batch_contact_sheet={batch_contact}")


if __name__ == "__main__":
    main()
