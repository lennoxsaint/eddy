"""Deterministic host-kernel edit candidates.

Host assistants express taste by selecting candidate ids. Eddy keeps ownership of the mechanical
timeline: candidate bounds come from transcript/audio evidence, then the normal compiler snaps,
protects, merges, and validates the final EDL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from eddy.edit.retakes import STOPWORDS, norm_word

CandidateKind = Literal["retake", "word_gap", "audio_silence", "filler_reset"]

OPENING_SCAN_S = 320.0
OPENING_BODY_STARTERS = (
    "the post",
    "someone",
    "first ",
    "step ",
    "now ",
    "next ",
    "failure ",
)
OPENING_HOOK_STARTERS = (
    "if ",
    "you are",
    "you're",
    "you can",
    "ive ",
    "i've ",
    "i'll ",
)


@dataclass(frozen=True)
class EditCandidate:
    id: str
    kind: CandidateKind
    start_s: float
    end_s: float
    reason: str
    quote: str = ""
    safety: str = "compiler_snaps_and_validates"
    source: str = "eddy_kernel"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OpeningHookVariant:
    id: str
    start_s: float
    end_s: float
    text: str
    word_count: int
    reason: str = "Opening hook attempt"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OpeningHookCluster:
    id: str
    start_s: float
    end_s: float
    default_variant_id: str
    policy: str
    variants: list[OpeningHookVariant]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["variants"] = [variant.to_dict() for variant in self.variants]
        return data


def _candidate_id(kind: str, start_s: float, end_s: float, index: int) -> str:
    start_ms = int(round(start_s * 1000))
    end_ms = int(round(end_s * 1000))
    return f"{kind}_{index:03d}_{start_ms:07d}_{end_ms:07d}"


def _stable_span_id(prefix: str, start_s: float, end_s: float, index: int) -> str:
    start_ms = int(round(start_s * 1000))
    end_ms = int(round(end_s * 1000))
    return f"{prefix}_{index:02d}_{start_ms:07d}_{end_ms:07d}"


def _round_time(value: float) -> float:
    return round(max(0.0, float(value)), 3)


def _norm_text(value: str) -> str:
    return " ".join(str(value).strip().split())


def _tokens(text: str) -> list[str]:
    return [norm_word(part) for part in str(text).split() if norm_word(part)]


def _info_count(tokens: list[str]) -> int:
    return sum(1 for token in tokens if token not in STOPWORDS and len(token) > 2)


def _words_text(words: list[dict], start_s: float, end_s: float, *, limit: int = 18) -> str:
    inside = [
        str(w.get("word", "")).strip()
        for w in words
        if float(w.get("start", 0.0)) >= start_s - 0.02 and float(w.get("end", 0.0)) <= end_s + 0.02
    ]
    return " ".join(" ".join(inside).split()[:limit])


def _phrase_rows(words: list[dict], phrases: list[dict] | None = None) -> list[dict]:
    if phrases:
        phrase_rows = []
        for phrase in phrases:
            text = _norm_text(str(phrase.get("text", "")))
            if not text:
                continue
            try:
                start = float(phrase["start"])
                end = float(phrase["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if end > start:
                phrase_rows.append({"start": _round_time(start), "end": _round_time(end), "text": text})
        return phrase_rows

    rows: list[dict] = []
    current: list[dict] = []
    for word in words:
        if current and float(word["start"]) - float(current[-1]["end"]) >= 1.0:
            rows.append(
                {
                    "start": _round_time(current[0]["start"]),
                    "end": _round_time(current[-1]["end"]),
                    "text": _norm_text("".join(str(w.get("word", "")) for w in current)),
                }
            )
            current = []
        current.append(word)
    if current:
        rows.append(
            {
                "start": _round_time(current[0]["start"]),
                "end": _round_time(current[-1]["end"]),
                "text": _norm_text("".join(str(w.get("word", "")) for w in current)),
            }
        )
    return [row for row in rows if row["text"]]


def _hook_chunks(rows: list[dict]) -> list[dict]:
    """Merge nearby transcript phrases into candidate opening-hook attempts."""

    chunks: list[dict] = []
    for row in rows:
        tokens = _tokens(row["text"])
        if len(tokens) < 3 or row["text"].lower() == "test.":
            continue
        if row["start"] > OPENING_SCAN_S:
            break
        text_l = row["text"].lower()
        if len(chunks) >= 2 and any(text_l.startswith(prefix) for prefix in OPENING_BODY_STARTERS):
            break
        starts_new_hook = any(text_l.startswith(prefix) for prefix in OPENING_HOOK_STARTERS)
        previous_is_clean = not retake_clean_failures([{"text": chunks[-1]["text"]}]) if chunks else True
        if chunks and (row["start"] - chunks[-1]["end"] <= 1.0 or (not starts_new_hook and previous_is_clean)):
            chunks[-1] = {
                "start": chunks[-1]["start"],
                "end": row["end"],
                "text": _norm_text(f"{chunks[-1]['text']} {row['text']}"),
            }
            continue
        chunks.append(dict(row))
    return chunks[:10]


def opening_hook_cluster(words: list[dict], phrases: list[dict] | None = None) -> OpeningHookCluster | None:
    """Find repeated opening hook attempts and recommend the last complete take.

    This is intentionally conservative: it only acts inside the initial opening scan and only when
    there are at least two plausible hook attempts. The selected/default variant is a keep target;
    the host-kernel compiler converts earlier variants into remove intervals.
    """

    chunks = _hook_chunks(_phrase_rows(words, phrases))
    if len(chunks) < 2:
        return None
    variants = [
        OpeningHookVariant(
            id=_stable_span_id("opening_hook_variant", chunk["start"], chunk["end"], idx + 1),
            start_s=_round_time(chunk["start"]),
            end_s=_round_time(chunk["end"]),
            text=chunk["text"],
            word_count=len(_tokens(chunk["text"])),
            reason="Candidate opening hook take",
        )
        for idx, chunk in enumerate(chunks)
    ]
    default = variants[-1]
    return OpeningHookCluster(
        id=_stable_span_id("opening_hook_cluster", variants[0].start_s, variants[-1].end_s, 1),
        start_s=variants[0].start_s,
        end_s=variants[-1].end_s,
        default_variant_id=default.id,
        policy="last_clean_hook_wins",
        variants=variants,
    )


def _short_hook_text(text: str) -> str:
    text = _norm_text(text)
    lower = text.lower()
    if any(word in lower for word in ("how", "why", "stop", "never", "truth", "secret")):
        return text[:140]
    if "duplicate" in lower and "codex" in lower:
        return "How to duplicate Codex and run any model inside it"
    if "local model" in lower or "local models" in lower:
        return "How local models keep your work on your laptop"
    if "api" in lower or "subscription" in lower:
        return "Why your AI coding route changes the cost"
    return text[:140]


def raw_short_candidates(
    phrases: list[dict],
    *,
    min_s: float = 10.0,
    max_s: float = 59.0,
    limit: int = 12,
) -> list[dict]:
    """Mine standalone short candidates from raw transcript phrases without model help."""

    rows = _phrase_rows([], phrases)
    candidates: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for i, start in enumerate(rows):
        words = _tokens(start["text"])
        if len(words) < 4:
            continue
        text_parts = [start["text"]]
        for j in range(i, min(len(rows), i + 8)):
            if j > i:
                text_parts.append(rows[j]["text"])
            span_s = rows[j]["end"] - start["start"]
            if span_s < min_s:
                continue
            if span_s > max_s + 5.0:
                break
            text = _norm_text(" ".join(text_parts))
            if len(_tokens(text)) < 18:
                continue
            key = (int(round(start["start"])), int(round(rows[j]["end"])))
            if key in seen:
                continue
            seen.add(key)
            hook = _short_hook_text(start["text"])
            candidates.append(
                {
                    "id": _stable_span_id("raw_short", start["start"], rows[j]["end"], len(candidates) + 1),
                    "start_s": _round_time(start["start"]),
                    "end_s": _round_time(rows[j]["end"]),
                    "hook": hook,
                    "reason": "Raw transcript miner found a complete standalone span.",
                    "text_preview": text[:260],
                    "duration_s": _round_time(span_s),
                }
            )
            break
    candidates.sort(key=lambda c: (-len(_tokens(c["text_preview"])), c["start_s"]))
    return candidates[:limit]


def retake_clean_failures(kept_phrases: list[dict], *, limit: int = 8) -> list[dict]:
    """Detect obvious surviving retakes from the kept transcript."""

    failures: list[dict] = []
    for phrase in kept_phrases:
        text = str(phrase.get("text", ""))
        tokens = _tokens(text)
        for n in (3, 2):
            for i in range(0, max(0, len(tokens) - (2 * n) + 1)):
                left = tokens[i : i + n]
                right = tokens[i + n : i + 2 * n]
                if left == right and _info_count(left) >= 1:
                    failures.append(
                        {
                            "type": "immediate_repeated_take",
                            "out_s": round(float(phrase.get("out_start", 0.0)), 2),
                            "quote": text[:160],
                            "ngram": " ".join(left),
                        }
                    )
                    break
            if failures and failures[-1].get("quote") == text[:160]:
                break
        if len(failures) >= limit:
            return failures

    return failures


def _span_around_word(words: list[dict], start_s: float) -> tuple[float, float]:
    for word in words:
        if abs(float(word.get("start", 0.0)) - start_s) <= 0.035:
            return _round_time(word["start"]), _round_time(word["end"])
    return _round_time(start_s), _round_time(start_s + 0.35)


def _retake_remove_end(words: list[dict], second_start_s: float) -> float:
    """Keep the second attempt. Remove up to the pause before it, leaving a small handle."""

    previous = [w for w in words if float(w.get("end", 0.0)) < second_start_s]
    if not previous:
        return _round_time(max(0.0, second_start_s - 0.18))
    return _round_time(min(second_start_s - 0.08, float(previous[-1]["end"]) + 0.05))


def _immediate_retake_spans(words: list[dict]) -> list[dict]:
    indexed = [
        {**word, "norm": norm_word(str(word.get("word", "")))}
        for word in words
        if norm_word(str(word.get("word", "")))
    ]
    spans: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for n in range(4, 1, -1):
        for i in range(0, len(indexed) - (2 * n) + 1):
            left = [str(w["norm"]) for w in indexed[i : i + n]]
            right = [str(w["norm"]) for w in indexed[i + n : i + (2 * n)]]
            if left != right or _info_count(left) < 1:
                continue
            start = float(indexed[i]["start"])
            first_end = float(indexed[i + n - 1]["end"])
            second_start = float(indexed[i + n]["start"])
            if second_start - first_end > 0.8:
                continue
            key = (int(round(start * 10)), int(round(second_start * 10)))
            if key in seen:
                continue
            seen.add(key)
            spans.append(
                {
                    "start_s": _round_time(start),
                    "end_s": _round_time(second_start),
                    "second_start_s": _round_time(second_start),
                    "phrase": " ".join(left),
                }
            )
    spans.sort(key=lambda item: (item["start_s"], -(item["end_s"] - item["start_s"])))
    filtered: list[dict] = []
    covered_until = -1.0
    for span in spans:
        if span["start_s"] < covered_until:
            continue
        filtered.append(span)
        covered_until = span["end_s"]
    return filtered


def _protected_majority_overlap(start_s: float, end_s: float, protected: list[dict]) -> bool:
    for span in protected:
        ps = float(span.get("start_s", span.get("start", 0.0)))
        pe = float(span.get("end_s", span.get("end", 0.0)))
        protected_len = max(0.1, pe - ps)
        overlap = min(end_s, pe) - max(start_s, ps)
        if overlap > 0 and overlap / protected_len > 0.5:
            return True
    return False


def build_edit_candidates(
    *,
    words: list[dict],
    transcript_gaps: list[dict] | None = None,
    audio_silence: list[dict] | None = None,
    retakes: list[dict] | None = None,
    fillers: list[dict] | None = None,
    protected_spans: list[dict] | None = None,
    max_candidates: int = 120,
) -> list[EditCandidate]:
    """Build deterministic candidate removals from local transcript/audio truth."""

    candidates: list[EditCandidate] = []
    protected = protected_spans or []
    counters: dict[str, int] = {"retake": 0, "word_gap": 0, "audio_silence": 0, "filler_reset": 0}

    def add(kind: CandidateKind, start_s: float, end_s: float, reason: str, **kwargs: Any) -> None:
        if end_s - start_s <= 0.05:
            return
        if _protected_majority_overlap(start_s, end_s, protected):
            return
        counters[kind] += 1
        candidates.append(
            EditCandidate(
                id=_candidate_id(kind, start_s, end_s, counters[kind]),
                kind=kind,
                start_s=_round_time(start_s),
                end_s=_round_time(end_s),
                reason=reason,
                **kwargs,
            )
        )

    for item in _immediate_retake_spans(words):
        add(
            "retake",
            float(item["start_s"]),
            float(item["end_s"]),
            "Immediate repeated phrase; remove the failed first attempt and keep the cleaner repeat.",
            quote=str(item["phrase"]),
            source="retake_clean_detector",
            metadata={
                "kept_take": "last",
                "second_start_s": item["second_start_s"],
                "immediate_repeat": True,
            },
        )

    for item in retakes or []:
        start_s = float(item.get("first_start_s", 0.0))
        second_start_s = float(item.get("second_start_s", 0.0))
        end_s = _retake_remove_end(words, second_start_s)
        phrase = str(item.get("phrase") or _words_text(words, start_s, min(end_s, start_s + 8.0)))
        add(
            "retake",
            start_s,
            end_s,
            "Earlier repeated take; keep the later attempt unless the host protects it.",
            quote=phrase,
            source="retake_detector",
            metadata={
                "kept_take": "last",
                "second_start_s": _round_time(second_start_s),
                "gap_s": item.get("gap_s"),
                "pause_before_second_s": item.get("pause_before_second_s"),
            },
        )

    for item in transcript_gaps or []:
        gap = float(item.get("gap_s", 0.0))
        if gap < 0.35:
            continue
        after_s = float(item.get("after_s", 0.0))
        start_s = after_s + 0.08
        end_s = after_s + gap - 0.08
        add(
            "word_gap",
            start_s,
            end_s,
            "Transcript-visible word gap; trims the center while preserving natural micro-pauses.",
            quote=f"{item.get('before_word', '')} ... {item.get('next_word', '')}".strip(),
            source="transcript_gap_map",
            metadata={"gap_s": round(gap, 3)},
        )

    for item in audio_silence or []:
        start_s = float(item.get("start", item.get("start_s", 0.0))) + 0.08
        end_s = float(item.get("end", item.get("end_s", 0.0))) - 0.08
        add(
            "audio_silence",
            start_s,
            end_s,
            "Audio-truth silence; removes silent motion without relying on transcript words.",
            quote=_words_text(words, max(0.0, start_s - 2.0), end_s + 2.0),
            source="audio_silence_map",
            metadata={"dur": item.get("dur")},
        )

    filler_words = {item.get("start_s"): item for item in fillers or []}
    by_start = {round(float(w.get("start", 0.0)), 2): w for w in words}
    for start, item in filler_words.items():
        if start is None:
            continue
        start_s, end_s = _span_around_word(words, float(start))
        word = by_start.get(round(float(start), 2), {}).get("word") or item.get("word") or ""
        if norm_word(str(word)) not in {"sorry", "okay", "wait"}:
            continue
        add(
            "filler_reset",
            start_s,
            end_s,
            "Filler/reset marker that often precedes a cleaner restart.",
            quote=str(word).strip(),
            source="filler_detector",
            metadata={"context": item.get("context", "")},
        )

    candidates.sort(key=lambda c: (c.start_s, c.end_s, c.kind, c.id))
    return candidates[:max_candidates]


def candidates_by_id(candidates: list[EditCandidate]) -> dict[str, EditCandidate]:
    return {candidate.id: candidate for candidate in candidates}
