from __future__ import annotations

from eddy.edit.kernel import build_edit_candidates
from eddy.edit.retakes import filler_candidates, retake_candidates
from eddy.edit.schema import EditDecisions
from eddy.edit.compiler import compile_edl
from eddy.config import EddyConfig


WORDS = [
    {"start": 0.10, "end": 0.35, "word": "here"},
    {"start": 0.45, "end": 0.70, "word": " is"},
    {"start": 0.80, "end": 1.05, "word": " the"},
    {"start": 1.15, "end": 1.45, "word": " point"},
    {"start": 2.50, "end": 2.75, "word": " here"},
    {"start": 2.85, "end": 3.10, "word": " is"},
    {"start": 3.20, "end": 3.45, "word": " the"},
    {"start": 3.55, "end": 3.85, "word": " point"},
    {"start": 4.70, "end": 4.95, "word": " wait"},
    {"start": 5.60, "end": 5.90, "word": " final"},
]


def test_kernel_retake_candidates_preserve_last_take_bias():
    candidates = build_edit_candidates(words=WORDS, retakes=retake_candidates(WORDS))
    retake = next(candidate for candidate in candidates if candidate.kind == "retake")

    assert retake.start_s < retake.metadata["second_start_s"]
    assert retake.end_s < retake.metadata["second_start_s"]
    assert retake.metadata["kept_take"] == "last"


def test_kernel_word_gap_candidates_keep_natural_handles():
    candidates = build_edit_candidates(
        words=WORDS,
        transcript_gaps=[{"after_s": 3.85, "gap_s": 0.85, "before_word": "point", "next_word": "wait"}],
    )
    gap = next(candidate for candidate in candidates if candidate.kind == "word_gap")

    assert gap.start_s == 3.93
    assert gap.end_s == 4.62
    assert "micro-pauses" in gap.reason


def test_kernel_audio_silence_candidates_skip_protected_spans():
    candidates = build_edit_candidates(
        words=WORDS,
        audio_silence=[
            {"start": 6.0, "end": 7.0, "dur": 1.0},
            {"start": 8.0, "end": 9.0, "dur": 1.0},
        ],
        protected_spans=[{"start_s": 5.8, "end_s": 7.1, "reason": "intentional pause"}],
    )

    assert [candidate.kind for candidate in candidates] == ["audio_silence"]
    assert candidates[0].start_s == 8.08


def test_kernel_selected_candidate_ids_compile_to_valid_edl():
    cfg = EddyConfig()
    candidates = build_edit_candidates(words=WORDS, retakes=retake_candidates(WORDS), fillers=filler_candidates(WORDS))
    retake = next(candidate for candidate in candidates if candidate.kind == "retake")
    decisions = EditDecisions(
        retakes=[
            {
                "remove_start_s": retake.start_s,
                "remove_end_s": retake.end_s,
                "kept_take": "last",
                "quote": retake.quote,
                "reason": retake.reason,
            }
        ]
    )

    edl = compile_edl(decisions, WORDS, "camera.mp4", 6.5, cfg.render, cfg.gates, silence_spans=[])

    assert edl.ranges
    assert edl.total_duration_s < 6.5
