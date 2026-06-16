"""Deterministic retake-candidate detection (port of vendor find_retake_candidates.py).

Runs on the RAW word timeline (pre-edit). Emits candidates as hints for the model;
the model adjudicates with last-take bias and emits actual remove ranges.
"""

from __future__ import annotations

import re
from collections import defaultdict

STOPWORDS = {
    "a", "and", "are", "as", "be", "because", "but", "for", "i", "if", "in", "is",
    "it", "of", "on", "or", "so", "that", "the", "then", "this", "to", "was", "we",
    "with", "you", "your",
}
FILLER_RESET_WORDS = {"sorry", "okay", "wait"}


def norm_word(value: str) -> str:
    value = value.lower().strip().replace("$", "")
    return re.sub(r"[^a-z0-9]+", "", value)


def _info_score(tokens: tuple[str, ...]) -> int:
    return sum(1 for t in tokens if t not in STOPWORDS and len(t) > 2)


def _context(words: list[dict], index: int, radius: int = 10) -> str:
    chunk = words[max(0, index - radius) : min(len(words), index + radius + 1)]
    return "".join(w["word"] for w in chunk).strip()


def retake_candidates(raw_words: list[dict], max_gap_s: float = 120.0, limit: int = 40) -> list[dict]:
    """Repeated 3-7 grams within `max_gap_s` of each other = likely retake pairs."""
    words = [
        {**w, "norm": norm_word(w["word"])}
        for w in raw_words
        if norm_word(w["word"])
    ]
    occurrences: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for n in range(3, 8):
        for i in range(len(words) - n + 1):
            tokens = tuple(w["norm"] for w in words[i : i + n])
            if _info_score(tokens) < 2:
                continue
            occurrences[tokens].append(i)

    candidates: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for tokens, indexes in occurrences.items():
        if len(indexes) < 2:
            continue
        for left, right in zip(indexes, indexes[1:]):
            gap = words[right]["start"] - words[left]["start"]
            if gap <= 1.0 or gap > max_gap_s:
                continue
            key = (round(words[left]["start"]), round(words[right]["start"]))
            if key in seen:
                continue
            seen.add(key)
            # Silence right before the second attempt is the classic retake tell (speaker stops,
            # then restarts). A near-zero pause is more likely natural repetition — the deliberate
            # recurrence of a key phrase, not a flub. We surface this as a HINT and let the model
            # adjudicate (detection stays permissive on purpose); it doesn't reorder candidates.
            pause_before = words[right]["start"] - words[right - 1]["end"] if right > 0 else 0.0
            candidates.append(
                {
                    "phrase": " ".join(tokens),
                    "score": _info_score(tokens) * len(tokens) - int(gap / 20),
                    "first_start_s": round(words[left]["start"], 2),
                    "second_start_s": round(words[right]["start"], 2),
                    "gap_s": round(gap, 1),
                    "pause_before_second_s": round(max(0.0, pause_before), 2),
                    "context_first": _context(words, left),
                    "context_second": _context(words, right),
                }
            )
    candidates.sort(key=lambda c: (-c["score"], c["gap_s"]))
    return candidates[:limit]


def filler_candidates(raw_words: list[dict], limit: int = 30) -> list[dict]:
    out = []
    words = [{**w, "norm": norm_word(w["word"])} for w in raw_words]
    for i, w in enumerate(words):
        if w["norm"] in FILLER_RESET_WORDS:
            out.append(
                {
                    "word": w["norm"],
                    "start_s": round(w["start"], 2),
                    "context": _context(words, i),
                }
            )
    return out[:limit]
