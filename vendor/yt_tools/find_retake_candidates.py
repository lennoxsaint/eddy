#!/usr/bin/env python3
"""Find likely remaining retakes in the current long-edit transcript map."""

from __future__ import annotations

import os
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("EDDY_YT_TOOLS_ROOT", "~/YouTube")).expanduser()
STOPWORDS = {
    "a",
    "and",
    "are",
    "as",
    "be",
    "because",
    "but",
    "for",
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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_word(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("$", "")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def fmt_time(seconds: float) -> str:
    minutes, sec = divmod(max(0.0, seconds), 60)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:05.2f}"
    return f"{minutes:d}:{sec:05.2f}"


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
                    "raw_start": float(word["start"]),
                    "raw_end": float(word["end"]),
                    "text": text,
                    "norm": normalized,
                }
            )
    return sorted(words, key=lambda item: (float(item["raw_start"]), float(item["raw_end"])))


def map_words_to_output(
    words: list[dict[str, Any]], segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    output_cursor = 0.0
    word_index = 0
    sorted_segments = sorted(segments, key=lambda item: (float(item["start"]), float(item["end"])))
    for segment in sorted_segments:
        start = float(segment["start"])
        end = float(segment["end"])
        while word_index < len(words) and float(words[word_index]["raw_end"]) < start:
            word_index += 1
        scan_index = word_index
        while scan_index < len(words) and float(words[scan_index]["raw_start"]) <= end:
            word = words[scan_index]
            midpoint = (float(word["raw_start"]) + float(word["raw_end"])) / 2
            if start <= midpoint <= end:
                mapped.append(
                    {
                        **word,
                        "out_start": output_cursor + float(word["raw_start"]) - start,
                        "out_end": output_cursor + float(word["raw_end"]) - start,
                    }
                )
            scan_index += 1
        output_cursor += end - start
    return mapped


def context(words: list[dict[str, Any]], index: int, radius: int = 12) -> str:
    selected = words[max(0, index - radius) : min(len(words), index + radius + 1)]
    return " ".join(str(word["text"]) for word in selected)


def info_score(tokens: tuple[str, ...]) -> int:
    return sum(1 for token in tokens if token not in STOPWORDS and len(token) > 2)


def repeated_ngram_candidates(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    occurrences: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for ngram_size in range(3, 8):
        for index in range(0, len(words) - ngram_size + 1):
            tokens = tuple(str(word["norm"]) for word in words[index : index + ngram_size])
            if info_score(tokens) < 2:
                continue
            occurrences[tokens].append(index)

    candidates: list[dict[str, Any]] = []
    seen_neighborhoods: set[tuple[int, int]] = set()
    for tokens, indexes in occurrences.items():
        if len(indexes) < 2:
            continue
        for left, right in zip(indexes, indexes[1:]):
            out_gap = float(words[right]["out_start"]) - float(words[left]["out_start"])
            if out_gap <= 1.0 or out_gap > 90.0:
                continue
            raw_gap = float(words[right]["raw_start"]) - float(words[left]["raw_start"])
            if raw_gap > 180.0:
                continue
            key = (round(float(words[left]["out_start"])), round(float(words[right]["out_start"])))
            if key in seen_neighborhoods:
                continue
            seen_neighborhoods.add(key)
            candidates.append(
                {
                    "phrase": " ".join(tokens),
                    "score": info_score(tokens) * len(tokens) - int(out_gap / 20),
                    "first_index": left,
                    "second_index": right,
                    "out_gap": out_gap,
                    "raw_gap": raw_gap,
                }
            )
    return sorted(candidates, key=lambda item: (-int(item["score"]), float(item["out_gap"])))


def filler_candidates(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    needles = {"sorry", "okay", "no", "wait"}
    candidates: list[dict[str, Any]] = []
    for index, word in enumerate(words):
        token = str(word["norm"])
        if token in needles:
            candidates.append(
                {
                    "phrase": token,
                    "score": 1,
                    "first_index": index,
                    "second_index": index,
                    "out_gap": 0.0,
                    "raw_gap": 0.0,
                }
            )
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--segments",
        type=Path,
        default=ROOT / "source/edit/keep_segments.long.retake_qa.json",
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        default=ROOT / "source/edit/transcript.faster-whisper.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "source/edit/remaining-retake-candidates.md",
    )
    parser.add_argument("--start-output", type=float, default=180.0)
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()

    words = map_words_to_output(transcript_words(args.transcript), load_json(args.segments)["segments"])
    repeated = [
        item
        for item in repeated_ngram_candidates(words)
        if float(words[int(item["first_index"])]["out_start"]) >= args.start_output
    ]
    filler = [
        item
        for item in filler_candidates(words)
        if float(words[int(item["first_index"])]["out_start"]) >= args.start_output
    ]

    lines = [
        "# Remaining Retake Candidates",
        "",
        f"- Transcript words in current keep list: {len(words)}",
        f"- Start output threshold: {fmt_time(args.start_output)}",
        "",
        "## Repeated Phrase Candidates",
        "",
        "| Rank | Phrase | Output Times | Raw Times | Context 1 | Context 2 |",
        "|---:|---|---|---|---|---|",
    ]
    for rank, candidate in enumerate(repeated[: args.limit], start=1):
        first = int(candidate["first_index"])
        second = int(candidate["second_index"])
        lines.append(
            "| "
            f"{rank} | {candidate['phrase']} | "
            f"{fmt_time(float(words[first]['out_start']))} / {fmt_time(float(words[second]['out_start']))} | "
            f"{float(words[first]['raw_start']):.3f} / {float(words[second]['raw_start']):.3f} | "
            f"{context(words, first)} | {context(words, second)} |"
        )

    lines.extend(
        [
            "",
            "## Filler/Reset Words To Spot-Check",
            "",
            "| Rank | Word | Output Time | Raw Time | Context |",
            "|---:|---|---:|---:|---|",
        ]
    )
    for rank, candidate in enumerate(filler[: args.limit], start=1):
        index = int(candidate["first_index"])
        lines.append(
            "| "
            f"{rank} | {candidate['phrase']} | {fmt_time(float(words[index]['out_start']))} | "
            f"{float(words[index]['raw_start']):.3f} | {context(words, index)} |"
        )

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
