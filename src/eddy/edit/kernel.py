"""Deterministic host-kernel edit candidates.

Host assistants express taste by selecting candidate ids. Eddy keeps ownership of the mechanical
timeline: candidate bounds come from transcript/audio evidence, then the normal compiler snaps,
protects, merges, and validates the final EDL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from eddy.edit.retakes import norm_word

CandidateKind = Literal["retake", "word_gap", "audio_silence", "filler_reset"]


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


def _candidate_id(kind: str, start_s: float, end_s: float, index: int) -> str:
    start_ms = int(round(start_s * 1000))
    end_ms = int(round(end_s * 1000))
    return f"{kind}_{index:03d}_{start_ms:07d}_{end_ms:07d}"


def _round_time(value: float) -> float:
    return round(max(0.0, float(value)), 3)


def _words_text(words: list[dict], start_s: float, end_s: float, *, limit: int = 18) -> str:
    inside = [
        str(w.get("word", "")).strip()
        for w in words
        if float(w.get("start", 0.0)) >= start_s - 0.02 and float(w.get("end", 0.0)) <= end_s + 0.02
    ]
    return " ".join(" ".join(inside).split()[:limit])


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
