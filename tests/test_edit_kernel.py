from __future__ import annotations

from eddy.edit.kernel import build_edit_candidates, opening_hook_cluster, raw_short_candidates, retake_clean_failures
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


def test_opening_hook_cluster_defaults_to_last_clean_hook():
    phrases = [
        {"start": 0.2, "end": 7.0, "text": "If you're using Codex you're probably using it wrong"},
        {"start": 9.0, "end": 18.0, "text": "If you are renting AI models the normal way this is better"},
        {"start": 20.0, "end": 31.0, "text": "You can duplicate Codex and run any model inside it"},
        {"start": 34.0, "end": 42.0, "text": "The post has the whole breakdown and scripts"},
    ]

    cluster = opening_hook_cluster([], phrases)

    assert cluster is not None
    assert len(cluster.variants) == 3
    assert cluster.default_variant_id == cluster.variants[-1].id
    assert "duplicate Codex" in cluster.variants[-1].text


def test_opening_hook_cluster_prefers_last_clean_hook_over_dirty_variant():
    phrases = [
        {"start": 34.0, "end": 43.9, "text": "You are renting your AI coding model and you don't have to"},
        {"start": 58.7, "end": 64.2, "text": "You are renting your AI coding model but you don't have to"},
        {"start": 242.1, "end": 255.7, "text": "You can duplicate you can duplicate the Codex app and run any model inside it"},
        {"start": 260.0, "end": 267.1, "text": "free local ones sitting right next to your normal Codex"},
        {"start": 274.8, "end": 280.6, "text": "I'll build the whole thing on screen"},
        {"start": 284.9, "end": 292.0, "text": "The post that went viral showed you the repo"},
    ]

    cluster = opening_hook_cluster([], phrases)

    assert cluster is not None
    assert cluster.default_variant_id == cluster.variants[-1].id
    assert cluster.variants[-3].start_s == 242.1
    assert cluster.variants[-3].end_s == 255.7
    assert cluster.variants[-2].start_s == 260.0
    assert cluster.variants[-1].start_s == 274.8
    assert cluster.variants[-1].end_s == 280.6
    assert cluster.variants[-1].text == "I'll build the whole thing on screen"


def test_kernel_immediate_retake_candidates_remove_first_duplicate_phrase():
    words = [
        {"start": 0.0, "end": 0.2, "word": " You"},
        {"start": 0.25, "end": 0.45, "word": " can"},
        {"start": 0.5, "end": 0.8, "word": " duplicate"},
        {"start": 0.9, "end": 1.1, "word": " you"},
        {"start": 1.15, "end": 1.35, "word": " can"},
        {"start": 1.4, "end": 1.7, "word": " duplicate"},
    ]

    candidates = build_edit_candidates(words=words)
    retake = next(candidate for candidate in candidates if candidate.kind == "retake")

    assert retake.start_s == 0.0
    assert retake.end_s == 0.9
    assert retake.metadata["immediate_repeat"] is True


def test_raw_short_candidates_mines_complete_transcript_spans():
    phrases = [
        {"start": 0.0, "end": 6.0, "text": "Here is how to duplicate Codex and run any model inside it"},
        {"start": 6.2, "end": 13.0, "text": "You copy the app route and change the model provider"},
        {"start": 13.3, "end": 22.0, "text": "That means you can test local models and subscription agents without rebuilding"},
    ]

    candidates = raw_short_candidates(phrases, min_s=10, max_s=59)

    assert candidates
    assert candidates[0]["id"].startswith("raw_short_")
    assert candidates[0]["start_s"] == 0.0
    assert candidates[0]["end_s"] >= 13.0
    assert "duplicate Codex" in candidates[0]["hook"]


def test_retake_clean_failures_detect_repeated_hooks_and_reset_loops():
    failures = retake_clean_failures(
        [
            {"out_start": 0.0, "text": "so today so today we are doing the real version"},
            {"out_start": 8.0, "text": "I've even got I've even got the build open"},
        ]
    )

    grams = {failure["ngram"] for failure in failures}
    assert "so today" in grams
    assert any("ive even got" in gram for gram in grams)
