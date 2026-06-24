"""Numeric/metric boundary safety for retention edits.

The whole point is narrow: keep Eddy aggressive everywhere except the handful of
words where clipping one syllable changes the truth. If an edit boundary touches
"104 clicks", "30.9K followers", "95 unique", or similar metric language, the
compiler widens only that boundary's handles.
"""

from __future__ import annotations

import re

NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
    "hundred", "thousand", "million", "billion", "k",
}

METRIC_WORDS = {
    "click", "clicks", "unique", "uniques", "follower", "followers", "view", "views", "percent",
    "percentage", "bot", "bots", "filtered", "filter", "link", "links", "lead", "leads",
    "conversion", "conversions", "revenue", "trial", "trials", "signup", "signups", "day", "days",
    "week", "weeks", "month", "months", "minute", "minutes", "second", "seconds", "rate",
    "engagement", "traffic",
}


def norm_token(word: str) -> str:
    return re.sub(r"[^a-z0-9.%]", "", str(word).lower())


def is_numeric_token(word: str) -> bool:
    token = norm_token(word)
    if not token:
        return False
    if token in NUMBER_WORDS:
        return True
    return bool(re.search(r"\d", token))


def is_metric_token(word: str) -> bool:
    return norm_token(word).rstrip("s") in {m.rstrip("s") for m in METRIC_WORDS}


def needs_numeric_boundary_guard(words: list[dict], first_idx: int, last_idx: int, window: int = 4) -> bool:
    """Return True when either edge is near a number and metric phrase.

    A plain year or step number does not always need wider pacing, so we require
    either a number at the edge or a metric near the edge, and a number/metric pair
    inside a small local window.
    """

    if not words:
        return False
    lo = max(0, min(first_idx, last_idx) - window)
    hi = min(len(words), max(first_idx, last_idx) + window + 1)
    local = [norm_token(w.get("word", "")) for w in words[lo:hi]]
    has_number = any(is_numeric_token(t) for t in local)
    has_metric = any(is_metric_token(t) for t in local)
    if not (has_number and has_metric):
        return False

    edge_lo = max(0, first_idx - 1)
    edge_hi = min(len(words), last_idx + 2)
    edge = [norm_token(w.get("word", "")) for w in words[edge_lo:edge_hi]]
    return any(is_numeric_token(t) or is_metric_token(t) for t in edge)


def guarded_ranges_report(ranges: list[dict], words: list[dict]) -> list[dict]:
    """Small receipt helper used by QA ledgers."""

    report: list[dict] = []
    for r in ranges:
        start = float(r["start"])
        end = float(r["end"])
        inside = [i for i, w in enumerate(words) if w["end"] >= start and w["start"] <= end]
        if not inside:
            continue
        if needs_numeric_boundary_guard(words, inside[0], inside[-1]):
            text = " ".join(str(words[i].get("word", "")) for i in inside)
            report.append({"start": round(start, 3), "end": round(end, 3), "text": text[:180]})
    return report
