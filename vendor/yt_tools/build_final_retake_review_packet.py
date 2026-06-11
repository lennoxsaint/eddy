#!/usr/bin/env python3
"""Build an audiovisual review packet for the rendered long retake-QA export."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path("/Users/yassybabes/YouTube")
FFMPEG = "/Users/yassybabes/.homebrew/bin/ffmpeg"
FFPROBE = "/Users/yassybabes/.homebrew/bin/ffprobe"

STOPWORDS = {
    "a",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "but",
    "for",
    "from",
    "i",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "so",
    "that",
    "the",
    "then",
    "this",
    "to",
    "was",
    "we",
    "with",
    "you",
    "your",
}
RESET_WORDS = {
    "actually",
    "again",
    "delete",
    "no",
    "okay",
    "rephrase",
    "sorry",
    "wait",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def media_duration(path: Path) -> float:
    result = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def fmt_time(seconds: float) -> str:
    minutes, sec = divmod(max(0.0, seconds), 60)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:05.2f}"
    return f"{minutes:d}:{sec:05.2f}"


def slug(value: str, limit: int = 64) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value[:limit].strip("-") or "clip"


def norm_word(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("$", "")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def transcript_words(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    words: list[dict[str, Any]] = []
    for segment in payload["segments"]:
        for word in segment.get("words", []):
            if "start" not in word or "end" not in word:
                continue
            text = str(word["word"]).strip()
            normalized = norm_word(text)
            if not normalized:
                continue
            words.append(
                {
                    "start": float(word["start"]),
                    "end": float(word["end"]),
                    "text": text,
                    "norm": normalized,
                    "probability": float(word.get("probability", 0.0) or 0.0),
                }
            )
    return sorted(words, key=lambda item: (float(item["start"]), float(item["end"])))


def info_score(tokens: tuple[str, ...]) -> int:
    return sum(1 for token in tokens if token not in STOPWORDS and len(token) > 2)


def context(words: list[dict[str, Any]], index: int, radius: int = 14) -> str:
    selected = words[max(0, index - radius) : min(len(words), index + radius + 1)]
    return " ".join(str(word["text"]) for word in selected).replace(" ,", ",")


def phrase_text(words: list[dict[str, Any]], index: int, length: int) -> str:
    return " ".join(str(word["text"]) for word in words[index : index + length])


def repeated_ngram_candidates(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    occurrences: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for ngram_size in range(3, 9):
        for index in range(0, len(words) - ngram_size + 1):
            tokens = tuple(str(word["norm"]) for word in words[index : index + ngram_size])
            if info_score(tokens) < 2:
                continue
            occurrences[tokens].append(index)

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for tokens, indexes in occurrences.items():
        if len(indexes) < 2:
            continue
        for left, right in zip(indexes, indexes[1:]):
            gap = float(words[right]["start"]) - float(words[left]["start"])
            if gap <= 0.8 or gap > 95.0:
                continue
            key = (round(float(words[left]["start"]) * 2), round(float(words[right]["start"]) * 2))
            if key in seen:
                continue
            seen.add(key)
            length = len(tokens)
            candidates.append(
                {
                    "kind": "repeated_phrase",
                    "phrase_norm": " ".join(tokens),
                    "phrase_text": phrase_text(words, left, length),
                    "first_index": left,
                    "second_index": right,
                    "length": length,
                    "gap": gap,
                    "score": info_score(tokens) * length - int(gap / 18),
                    "context_1": context(words, left),
                    "context_2": context(words, right),
                }
            )
    return sorted(candidates, key=lambda item: (-int(item["score"]), float(item["gap"])))


def reset_candidates(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, word in enumerate(words):
        token = str(word["norm"])
        if token not in RESET_WORDS:
            continue
        candidates.append(
            {
                "kind": "reset_word",
                "phrase_norm": token,
                "phrase_text": str(word["text"]),
                "first_index": index,
                "second_index": index,
                "length": 1,
                "gap": 0.0,
                "score": 1,
                "context_1": context(words, index),
                "context_2": "",
            }
        )
    return candidates


def output_to_raw_maps(segments: list[dict[str, Any]]) -> list[dict[str, float]]:
    output_cursor = 0.0
    mapped: list[dict[str, float]] = []
    for segment in sorted(segments, key=lambda item: (float(item["start"]), float(item["end"]))):
        raw_start = float(segment["start"])
        raw_end = float(segment["end"])
        duration = raw_end - raw_start
        mapped.append(
            {
                "out_start": output_cursor,
                "out_end": output_cursor + duration,
                "raw_start": raw_start,
                "raw_end": raw_end,
            }
        )
        output_cursor += duration
    return mapped


def output_to_raw(mapped: list[dict[str, float]], seconds: float) -> float | None:
    for item in mapped:
        if item["out_start"] <= seconds <= item["out_end"]:
            return item["raw_start"] + (seconds - item["out_start"])
    return None


def export_video_clip(source: Path, output: Path, start: float, duration: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, start):.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-vf",
            "scale=960:-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def export_waveform(source: Path, output: Path, start: float, duration: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, start):.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
            "-filter_complex",
            "aformat=channel_layouts=mono,showwavespic=s=1200x220:colors=0x2f8cff",
            "-frames:v",
            "1",
            str(output),
        ]
    )


def export_contact_sheet(source: Path, output: Path, start: float, duration: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    # One image every third of the window, tiled horizontally.
    frame_step = max(0.5, duration / 3.0)
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, start):.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
            "-vf",
            f"fps=1/{frame_step:.3f},scale=360:-1,tile=3x1",
            "-frames:v",
            "1",
            str(output),
        ]
    )


def chunk_rows(
    words: list[dict[str, Any]],
    duration: float,
    chunk_seconds: float,
    out_dir: Path,
    video: Path,
) -> list[str]:
    chunk_label = f"{chunk_seconds:g}-Second"
    rows = [
        f"## {chunk_label} Chunk Review Index",
        "",
        "| Chunk | Range | Waveform | Frames | Transcript Excerpt | Flags |",
        "|---:|---|---|---|---|---|",
    ]
    chunk_count = math.ceil(duration / chunk_seconds)
    for chunk_index in range(chunk_count):
        start = chunk_index * chunk_seconds
        end = min(duration, start + chunk_seconds)
        selected = [word for word in words if start <= float(word["start"]) < end]
        excerpt = " ".join(str(word["text"]) for word in selected[:55]).replace("|", "\\|")
        flags = sorted({str(word["norm"]) for word in selected if str(word["norm"]) in RESET_WORDS})
        wave = out_dir / "chunks" / f"chunk-{chunk_index + 1:02d}-waveform.png"
        sheet = out_dir / "chunks" / f"chunk-{chunk_index + 1:02d}-frames.jpg"
        export_waveform(video, wave, start, end - start)
        export_contact_sheet(video, sheet, start, end - start)
        rows.append(
            "| "
            f"{chunk_index + 1} | {fmt_time(start)}-{fmt_time(end)} | "
            f"`{wave}` | `{sheet}` | {excerpt} | {', '.join(flags) or 'none'} |"
        )
    return rows


def candidate_rows(
    words: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    mapped: list[dict[str, float]],
    out_dir: Path,
    video: Path,
    limit: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    rows = [
        "## Candidate Clip Pairs",
        "",
        "| # | Kind | Phrase | Output Times | Raw Times | Evidence | Context / Decision Notes |",
        "|---:|---|---|---|---|---|---|",
    ]
    data: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates[:limit], start=1):
        first = int(candidate["first_index"])
        second = int(candidate["second_index"])
        length = int(candidate["length"])
        first_start = float(words[first]["start"])
        first_end = float(words[min(len(words) - 1, first + length - 1)]["end"])
        second_start = float(words[second]["start"])
        second_end = float(words[min(len(words) - 1, second + length - 1)]["end"])
        label = f"{index:03d}-{slug(str(candidate['phrase_text']))}"
        evidence_parts = []
        for suffix, start, end in (
            ("a", first_start, first_end),
            ("b", second_start, second_end),
        ):
            clip_start = max(0.0, start - 4.0)
            clip_duration = min(18.0, max(8.0, (end - start) + 8.0))
            clip = out_dir / "clips" / f"{label}-{suffix}.mp4"
            wave = out_dir / "waveforms" / f"{label}-{suffix}.png"
            sheet = out_dir / "frames" / f"{label}-{suffix}.jpg"
            export_video_clip(video, clip, clip_start, clip_duration)
            export_waveform(video, wave, clip_start, clip_duration)
            export_contact_sheet(video, sheet, clip_start, clip_duration)
            evidence_parts.append(f"{suffix}: [`clip`]({clip}) [`wave`]({wave}) [`frames`]({sheet})")
        first_raw = output_to_raw(mapped, first_start)
        second_raw = output_to_raw(mapped, second_start)
        row_data = {
            **candidate,
            "rank": index,
            "first_output_start": first_start,
            "first_output_end": first_end,
            "second_output_start": second_start,
            "second_output_end": second_end,
            "first_raw_start": first_raw,
            "second_raw_start": second_raw,
        }
        data.append(row_data)
        raw_display = (
            f"{first_raw:.3f} / {second_raw:.3f}"
            if first_raw is not None and second_raw is not None
            else "UNKNOWN"
        )
        decision_hint = "REVIEW: compare clips; remove only if one is an abandoned take."
        if candidate["kind"] == "reset_word":
            decision_hint = "SPOT-CHECK: reset word may be normal usage; remove only if followed by a restart."
        rows.append(
            "| "
            f"{index} | {candidate['kind']} | {candidate['phrase_text'].replace('|', '/')} | "
            f"{fmt_time(first_start)} / {fmt_time(second_start)} | {raw_display} | "
            f"{'<br>'.join(evidence_parts)} | "
            f"{candidate['context_1'].replace('|', '/')}<br>{candidate.get('context_2', '').replace('|', '/')}<br>{decision_hint} |"
        )
    return rows, data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--video",
        type=Path,
        default=ROOT
        / "source/exports/Codex-2026-05-29-landed-2300-month-client-long-retake-qa-final.mp4",
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        default=ROOT / "source/edit/final-retake-qa-transcript.faster-whisper.json",
    )
    parser.add_argument(
        "--segments",
        type=Path,
        default=ROOT / "source/edit/keep_segments.long.retake_qa.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "source/exports/qa/final-retake-review-packet",
    )
    parser.add_argument("--candidate-limit", type=int, default=60)
    parser.add_argument("--chunk-seconds", type=float, default=60.0)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    duration = media_duration(args.video)
    words = transcript_words(args.transcript)
    segments = load_json(args.segments)["segments"]
    mapped = output_to_raw_maps(segments)
    repeated = repeated_ngram_candidates(words)
    resets = reset_candidates(words)
    candidates = repeated + resets

    rows = [
        "# Final Retake Review Packet",
        "",
        f"- Source video: `{args.video}`",
        f"- Source transcript: `{args.transcript}`",
        f"- Duration: {duration:.3f}s ({fmt_time(duration)})",
        f"- Word count from final ASR: {len(words)}",
        f"- Repeated phrase candidates: {len(repeated)}",
        f"- Reset-word spot checks: {len(resets)}",
        "",
    ]
    rows.extend(
        chunk_rows(
            words=words,
            duration=duration,
            chunk_seconds=args.chunk_seconds,
            out_dir=args.out_dir,
            video=args.video,
        )
    )
    rows.append("")
    candidate_md, candidate_data = candidate_rows(
        words=words,
        candidates=candidates,
        mapped=mapped,
        out_dir=args.out_dir,
        video=args.video,
        limit=args.candidate_limit,
    )
    rows.extend(candidate_md)

    manifest = args.out_dir / "manifest.md"
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")
    (args.out_dir / "candidate-data.json").write_text(
        json.dumps(candidate_data, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {manifest}")
    print(f"Wrote {args.out_dir / 'candidate-data.json'}")


if __name__ == "__main__":
    main()
