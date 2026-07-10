"""Deterministic editorial evidence for host-authored Eddy plans."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class _Phrase:
    index: int
    start: float
    end: float
    text: str
    tokens: tuple[str, ...]


def build_editorial_ledger(
    transcript: Path,
    *,
    audio: Path | None = None,
    silence_spans: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Build stable repeat, reset, and long-gap candidates from word timings."""

    payload = json.loads(transcript.read_text())
    words = [word for word in payload.get("words", []) if _valid_word(word)]
    phrases = _phrases(words)
    candidates = _repeat_candidates(phrases)
    candidates.extend(_reset_candidates(phrases))
    candidates.extend(_false_start_candidates(phrases))
    candidates.extend(_long_gap_candidates(words))
    measured_silences = silence_spans if silence_spans is not None else _audio_silences(audio)
    candidates.extend(_audio_gap_candidates(measured_silences))
    candidates = _deduplicate_long_gaps(candidates)
    candidates.sort(key=lambda item: (float(item["start"]), str(item["id"])))
    duration = max((float(word["end"]) for word in words), default=0.0)
    return {
        "schema_version": "editorial-ledger-v1",
        "duration": round(duration, 3),
        "chunks": _chunks(words, duration),
        "candidates": candidates,
        "policy": {
            "last_clean_take_default": True,
            "protected_pause_ceiling_s": 0.8,
            "requires_full_coverage": True,
        },
    }


def validate_editorial_review(ledger: dict[str, Any], review: dict[str, Any]) -> list[str]:
    """Return exact blockers for missing transcript coverage or candidate decisions."""

    blockers: list[str] = []
    coverage = review.get("coverage", [])
    for chunk in ledger.get("chunks", []):
        start, end = float(chunk["start"]), float(chunk["end"])
        if not _range_covered(start, end, coverage):
            blockers.append(f"editorial_chunk_unreviewed:{chunk['id']}")
    resolutions = {
        item.get("candidate_id"): item
        for item in review.get("resolutions", [])
        if isinstance(item, dict) and item.get("candidate_id")
    }
    for candidate in ledger.get("candidates", []):
        candidate_id = candidate.get("id")
        if candidate.get("requires_resolution", True) and candidate_id not in resolutions:
            blockers.append(f"editorial_candidate_unresolved:{candidate_id}")
            continue
        resolution = resolutions.get(candidate_id)
        if resolution is None:
            continue
        action = resolution.get("action")
        kind = candidate.get("kind")
        variants = {
            item.get("id")
            for item in candidate.get("variants", [])
            if isinstance(item, dict) and item.get("id")
        }
        selected = resolution.get("selected_variant_id")
        if action == "keep_variant" and selected not in variants:
            blockers.append(f"editorial_selected_variant_unknown:{candidate_id}")
        if action == "keep_last" and not candidate.get("recommended_variant_id"):
            blockers.append(f"editorial_keep_last_unavailable:{candidate_id}")
        if kind == "long_gap" and action not in {"tighten_gap", "drop_all"}:
            blockers.append(f"editorial_long_gap_action_invalid:{candidate_id}")
    return blockers


def _valid_word(word: object) -> bool:
    if not isinstance(word, dict):
        return False
    try:
        return bool(str(word.get("word", "")).strip()) and float(word["end"]) > float(word["start"])
    except (KeyError, TypeError, ValueError):
        return False


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _phrases(words: list[dict[str, Any]]) -> list[_Phrase]:
    if not words:
        return []
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        if current and float(word["start"]) - float(current[-1]["end"]) > 0.8:
            groups.append(current)
            current = []
        current.append(word)
        token = str(word["word"]).strip()
        if token.endswith((".", "?", "!", "...")) or len(current) >= 24:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    phrases: list[_Phrase] = []
    for index, group in enumerate(groups):
        tokens = tuple(token for token in (_normalize(str(item["word"])) for item in group) if token)
        if not tokens:
            continue
        phrases.append(
            _Phrase(
                index=index,
                start=float(group[0]["start"]),
                end=float(group[-1]["end"]),
                text=" ".join(str(item["word"]) for item in group),
                tokens=tokens,
            )
        )
    return phrases


def _repeat_candidates(phrases: list[_Phrase]) -> list[dict[str, Any]]:
    edges: dict[int, set[int]] = {phrase.index: set() for phrase in phrases}
    by_index = {phrase.index: phrase for phrase in phrases}
    for left_pos, left in enumerate(phrases):
        for right in phrases[left_pos + 1 :]:
            similarity = SequenceMatcher(
                a=left.tokens,
                b=right.tokens,
                autojunk=False,
            )
            shared = _shares_ngram(left.tokens, right.tokens, 4)
            containment = similarity.find_longest_match().size / max(
                1,
                min(len(left.tokens), len(right.tokens)),
            )
            related_repeat = shared and (similarity.ratio() >= 0.45 or containment >= 0.65)
            nearby_fuzzy = (
                min(len(left.tokens), len(right.tokens)) >= 3
                and
                right.start - left.start <= 120.0
                and similarity.ratio() >= 0.78
            )
            if related_repeat or nearby_fuzzy:
                edges[left.index].add(right.index)
                edges[right.index].add(left.index)

    candidates: list[dict[str, Any]] = []
    visited: set[int] = set()
    for phrase in phrases:
        if phrase.index in visited or not edges[phrase.index]:
            continue
        stack = [phrase.index]
        component: list[_Phrase] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(by_index[current])
            stack.extend(sorted(edges[current] - visited))
        component.sort(key=lambda item: item.start)
        if len(component) < 2:
            continue
        variants = [
            {
                "id": _stable_id("variant", item.start, item.end, item.text),
                "start": round(item.start, 3),
                "end": round(item.end, 3),
                "text": item.text,
            }
            for item in component
        ]
        candidates.append(
            {
                "id": _stable_id("repeat", component[0].start, component[-1].end, component[-1].text),
                "kind": "repeat",
                "start": round(component[0].start, 3),
                "end": round(component[-1].end, 3),
                "variants": variants,
                "recommended_variant_id": variants[-1]["id"],
                "requires_resolution": True,
            }
        )
    return candidates


def _reset_candidates(phrases: list[_Phrase]) -> list[dict[str, Any]]:
    reset_phrases = [phrase for phrase in phrases if _is_reset_phrase(phrase)]
    groups: list[list[_Phrase]] = []
    current: list[_Phrase] = []
    for phrase in reset_phrases:
        if current and phrase.start - current[-1].end > 20.0:
            if len(current) >= 2:
                groups.append(current)
            current = []
        current.append(phrase)
    if len(current) >= 2:
        groups.append(current)

    candidates: list[dict[str, Any]] = []
    for group in groups:
        if not _looks_like_reset_loop(group):
            continue
        variants = [
            {
                "id": _stable_id("variant", phrase.start, phrase.end, phrase.text),
                "start": round(phrase.start, 3),
                "end": round(phrase.end, 3),
                "text": phrase.text,
            }
            for phrase in group
        ]
        candidates.append(
            {
                "id": _stable_id("reset", group[0].start, group[-1].end, group[-1].text),
                "kind": "reset_loop",
                "start": round(group[0].start, 3),
                "end": round(group[-1].end, 3),
                "variants": variants,
                "recommended_variant_id": variants[-1]["id"],
                "requires_resolution": True,
            }
        )
    return candidates


def _looks_like_reset_loop(group: list[_Phrase]) -> bool:
    if any(len(phrase.tokens) <= 2 or phrase.text.rstrip().endswith("...") for phrase in group):
        return True
    return any(
        SequenceMatcher(
            a=left.tokens,
            b=right.tokens,
            autojunk=False,
        ).ratio()
        >= 0.65
        for left, right in zip(group, group[1:], strict=False)
    )


def _false_start_candidates(phrases: list[_Phrase]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    trailing = {"and", "but", "because", "so", "the", "a", "an", "to", "of"}
    for phrase in phrases:
        raw_last = phrase.text.rstrip().split()[-1].lower()
        unfinished = raw_last.endswith("...") or (
            len(phrase.tokens) <= 8 and phrase.tokens[-1] in trailing
        )
        if not unfinished:
            continue
        candidates.append(
            {
                "id": _stable_id("false-start", phrase.start, phrase.end, phrase.text),
                "kind": "false_start",
                "start": round(phrase.start, 3),
                "end": round(phrase.end, 3),
                "text": phrase.text,
                "requires_resolution": True,
            }
        )
    return candidates


def _is_reset_phrase(phrase: _Phrase) -> bool:
    if not phrase.tokens:
        return False
    if phrase.tokens[0] in {"okay", "ok", "so", "right", "sorry", "anyway"}:
        return True
    return len(phrase.tokens) >= 2 and phrase.tokens[:2] in {("let", "me"), ("hang", "on")}


def _long_gap_candidates(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for left, right in zip(words, words[1:], strict=False):
        start, end = float(left["end"]), float(right["start"])
        if end - start <= 0.8:
            continue
        candidates.append(
            {
                "id": _stable_id("gap", start, end, f"{left['word']}|{right['word']}"),
                "kind": "long_gap",
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "before": str(left["word"]),
                "after": str(right["word"]),
                "source": "transcript",
                "requires_resolution": True,
            }
        )
    return candidates


def _audio_silences(audio: Path | None) -> list[list[float]]:
    if audio is None:
        return []
    process = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(audio),
            "-vn",
            "-af",
            "silencedetect=noise=-30dB:d=0.8",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    spans: list[list[float]] = []
    pending: float | None = None
    for line in process.stderr.splitlines():
        if "silence_start:" in line:
            try:
                pending = float(line.split("silence_start:", 1)[1].strip())
            except ValueError:
                pending = None
        elif "silence_end:" in line and pending is not None:
            try:
                end = float(line.split("silence_end:", 1)[1].split("|", 1)[0].strip())
            except ValueError:
                pending = None
                continue
            spans.append([pending, end])
            pending = None
    return spans


def _audio_gap_candidates(spans: list[list[float]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for start, end in spans:
        if end - start <= 0.8:
            continue
        candidates.append(
            {
                "id": _stable_id("audio-gap", start, end, "audio-silence"),
                "kind": "long_gap",
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "source": "audio",
                "requires_resolution": True,
            }
        )
    return candidates


def _deduplicate_long_gaps(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    other = [candidate for candidate in candidates if candidate.get("kind") != "long_gap"]
    gaps = sorted(
        (candidate for candidate in candidates if candidate.get("kind") == "long_gap"),
        key=lambda candidate: float(candidate["start"]),
    )
    merged: list[dict[str, Any]] = []
    for gap in gaps:
        start, end = float(gap["start"]), float(gap["end"])
        if not merged or start > float(merged[-1]["end"]):
            merged.append(dict(gap))
            continue
        current = merged[-1]
        current["start"] = round(min(float(current["start"]), start), 3)
        current["end"] = round(max(float(current["end"]), end), 3)
        current["duration"] = round(float(current["end"]) - float(current["start"]), 3)
        sources = {
            str(current.get("source", "transcript")),
            str(gap.get("source", "transcript")),
        }
        current["source"] = "+".join(sorted(sources))
        current["id"] = _stable_id(
            "gap",
            float(current["start"]),
            float(current["end"]),
            str(current["source"]),
        )
    return [*other, *merged]


def _shares_ngram(left: tuple[str, ...], right: tuple[str, ...], size: int) -> bool:
    if len(left) < size or len(right) < size:
        return False
    left_grams = {left[index : index + size] for index in range(len(left) - size + 1)}
    return any(right[index : index + size] in left_grams for index in range(len(right) - size + 1))


def _chunks(words: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    start = 0.0
    while start < duration or (not chunks and words):
        end = min(duration, start + 60.0)
        text = " ".join(
            str(word["word"])
            for word in words
            if float(word["start"]) < end and float(word["end"]) > start
        )
        chunks.append(
            {
                "id": f"chunk-{len(chunks) + 1:03d}",
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
            }
        )
        if end <= start:
            break
        start = end
    return chunks


def _range_covered(start: float, end: float, coverage: object) -> bool:
    if not isinstance(coverage, list):
        return False
    cursor = start
    for item in sorted(coverage):
        if not isinstance(item, list) or len(item) != 2:
            continue
        item_start, item_end = float(item[0]), float(item[1])
        if item_start > cursor + 0.01:
            continue
        if item_end >= cursor:
            cursor = max(cursor, item_end)
        if cursor >= end - 0.01:
            return True
    return False


def _stable_id(prefix: str, start: float, end: float, text: str) -> str:
    digest = hashlib.sha256(f"{start:.3f}|{end:.3f}|{text}".encode()).hexdigest()[:12]
    return f"{prefix}-{digest}"
