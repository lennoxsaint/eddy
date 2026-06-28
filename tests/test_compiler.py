"""Compiler invariants on synthetic transcripts."""

import pytest

from eddy.config import GatesConfig, RenderConfig
from eddy.edit.compiler import CompileError, compile_edl, cut_transcript, cut_word_transcript, gap_tighten_intervals
from eddy.edit.schema import Cut, EditDecisions, Edl, EdlRange, ProtectedMoment, Retake

RENDER = RenderConfig()
GATES = GatesConfig()


def make_words(*, n=100, word_s=0.3, gap_s=0.1, start=0.0):
    """n words, each word_s long with gap_s between."""
    words, t = [], start
    for i in range(n):
        words.append({"start": round(t, 3), "end": round(t + word_s, 3), "word": f" w{i}", "probability": 0.9})
        t += word_s + gap_s
    return words


def total_dur(words, tail=1.0):
    return words[-1]["end"] + tail


def test_no_cuts_keeps_everything():
    words = make_words()
    d = EditDecisions()
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    assert len(edl.ranges) == 1
    r = edl.ranges[0]
    assert r.start <= words[0]["start"]
    assert r.end >= words[-1]["end"]


def test_cut_removes_words_and_snaps_to_boundaries():
    words = make_words()
    # cut covering words 20..39 (raw seconds)
    cut_start, cut_end = words[20]["start"], words[39]["end"]
    d = EditDecisions(cuts=[Cut(start_s=cut_start, end_s=cut_end, tier="MANDATORY")])
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    assert len(edl.ranges) == 2
    first, second = edl.ranges
    # first range must end after word 19 ends but before word 20 starts
    assert words[19]["end"] <= first.end <= words[20]["start"]
    # second range must start before word 40 starts but after word 39 ends
    assert words[39]["end"] <= second.start <= words[40]["start"]


def test_pads_never_reach_neighbor_words():
    words = make_words(gap_s=0.04)  # gap smaller than pad_after (80ms)
    cut_start, cut_end = words[50]["start"], words[59]["end"]
    d = EditDecisions(cuts=[Cut(start_s=cut_start, end_s=cut_end, tier="MANDATORY")])
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    first, second = edl.ranges
    assert first.end <= words[50]["start"]  # never into the first removed word
    assert second.start >= words[49]["end"]  # never into the last kept word


def test_overlapping_cuts_merge():
    words = make_words()
    d = EditDecisions(
        cuts=[
            Cut(start_s=words[10]["start"], end_s=words[30]["end"], tier="MANDATORY"),
            Cut(start_s=words[25]["start"], end_s=words[45]["end"], tier="RECOMMENDED"),
        ]
    )
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    assert len(edl.ranges) == 2


def test_retake_plus_cut_both_removed():
    words = make_words()
    d = EditDecisions(
        retakes=[Retake(remove_start_s=words[5]["start"], remove_end_s=words[15]["end"])],
        cuts=[Cut(start_s=words[60]["start"], end_s=words[70]["end"], tier="MANDATORY")],
    )
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    assert len(edl.ranges) == 3
    total = sum(r.end - r.start for r in edl.ranges)
    assert total < total_dur(words)


def test_protected_moment_wins_cut_gets_clipped():
    words = make_words()
    # cut spans words 10..20 but words 13..18 are protected (substantial overlap):
    # the protected words must survive in a kept range
    d = EditDecisions(
        cuts=[Cut(start_s=words[10]["start"], end_s=words[20]["end"], tier="MANDATORY")],
        protected_moments=[ProtectedMoment(start_s=words[13]["start"], end_s=words[18]["end"])],
    )
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    w15 = words[15]
    assert any(r.start <= w15["start"] and w15["end"] <= r.end for r in edl.ranges)
    # while an unprotected cut word stays out
    w11 = words[11]
    assert not any(r.start <= w11["start"] and w11["end"] <= r.end for r in edl.ranges)


def test_self_contradiction_protection_equals_cut():
    words = make_words()
    # model protects and cuts the exact same span: protection wins, content survives
    span = (words[30]["start"], words[40]["end"])
    d = EditDecisions(
        cuts=[Cut(start_s=span[0], end_s=span[1], tier="MANDATORY")],
        protected_moments=[ProtectedMoment(start_s=span[0], end_s=span[1])],
    )
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    assert len(edl.ranges) == 1  # nothing actually removed


def test_protected_moment_tiny_filler_trim_allowed():
    words = make_words()
    # 0.7s trim inside a 20s protected beat: legitimate filler removal
    d = EditDecisions(
        cuts=[Cut(start_s=words[30]["start"], end_s=words[31]["end"], tier="MANDATORY")],
        protected_moments=[ProtectedMoment(start_s=words[15]["start"], end_s=words[65]["end"])],
    )
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    assert len(edl.ranges) == 2


def test_inverted_and_out_of_bounds_rejected():
    words = make_words()
    d = EditDecisions(cuts=[Cut(start_s=50.0, end_s=10.0, tier="MANDATORY")])
    with pytest.raises(CompileError):
        compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES)
    d2 = EditDecisions(cuts=[Cut(start_s=10.0, end_s=99999.0, tier="MANDATORY")])
    with pytest.raises(CompileError):
        compile_edl(d2, words, "cam.mp4", total_dur(words), RENDER, GATES)


def test_everything_cut_raises_empty_edit():
    words = make_words()
    d = EditDecisions(cuts=[Cut(start_s=0.0, end_s=total_dur(words), tier="MANDATORY")])
    with pytest.raises(CompileError) as e:
        compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES)
    assert e.value.problems[0]["type"] == "empty_edit"


def test_gap_tightening_cuts_center_leaves_handles():
    words = make_words(n=10, gap_s=0.1)
    # inject a 3s gap between word 4 and 5
    shift = 3.0
    for w in words[5:]:
        w["start"] = round(w["start"] + shift, 3)
        w["end"] = round(w["end"] + shift, 3)
    intervals = gap_tighten_intervals(words)
    assert len(intervals) == 1
    s, e = intervals[0]
    # tightened gaps now leave a short fade-safe handle each side (was 0.25s) — tighter pacing
    from eddy.edit.compiler import GAP_LEAVE_HANDLE_S
    assert s == pytest.approx(words[4]["end"] + GAP_LEAVE_HANDLE_S, abs=0.005)
    assert e == pytest.approx(words[5]["start"] - GAP_LEAVE_HANDLE_S, abs=0.005)


def test_gap_tightening_catches_sub_silent_motion_threshold_pause():
    from eddy.edit.compiler import GAP_LEAVE_HANDLE_S

    words = make_words(n=4, gap_s=0.1)
    # 0.5s pauses are below the old 0.68s threshold but still trip the rendered
    # silent_motion gate once encoder/fade tails are included.
    shift = 0.5
    for w in words[2:]:
        w["start"] = round(w["start"] + shift, 3)
        w["end"] = round(w["end"] + shift, 3)
    intervals = gap_tighten_intervals(words)
    assert intervals
    assert intervals[0][0] == pytest.approx(words[1]["end"] + GAP_LEAVE_HANDLE_S, abs=0.005)


def test_debris_ranges_dropped():
    words = make_words()
    # two cuts leaving a single word (~0.3s < min_range 1.2s) between them
    d = EditDecisions(
        cuts=[
            Cut(start_s=words[10]["start"], end_s=words[20]["end"], tier="MANDATORY"),
            Cut(start_s=words[22]["start"], end_s=words[30]["end"], tier="MANDATORY"),
        ]
    )
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    for r in edl.ranges:
        assert r.end - r.start >= GATES.min_range_s
    # word 21 must not be in any kept range
    w21 = words[21]
    assert not any(r.start <= w21["start"] and w21["end"] <= r.end for r in edl.ranges)


def test_cut_transcript_output_timeline_monotonic():
    words = make_words()
    phrases = [
        {"start": words[i]["start"], "end": words[min(i + 9, len(words) - 1)]["end"],
         "text": f"phrase {i}"}
        for i in range(0, 100, 10)
    ]
    d = EditDecisions(cuts=[Cut(start_s=words[30]["start"], end_s=words[49]["end"], tier="MANDATORY")])
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    kept = cut_transcript(edl, phrases)
    outs = [p["out_start"] for p in kept]
    assert outs == sorted(outs)
    assert len(kept) < len(phrases)


def test_benchmark_format_roundtrip():
    words = make_words()
    d = EditDecisions(cuts=[Cut(start_s=words[10]["start"], end_s=words[20]["end"], tier="MANDATORY")])
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    bench = edl.to_benchmark_format(slug="t")
    assert len(bench["ranges"]) == len(edl.ranges)
    for br, er in zip(bench["ranges"], edl.ranges):
        assert br["start"] == er.start and br["end"] == er.end
        assert abs(br["duration"] - (er.end - er.start)) < 0.005


def test_word_cut_transcript_does_not_overinclude_partial_phrase_tail():
    edl = Edl(
        sources={"camera": "cam.mp4"},
        ranges=[EdlRange(start=10.0, end=12.0)],
        total_duration_s=2.0,
    )
    words = [
        {"start": 10.0, "end": 10.4, "word": " real"},
        {"start": 10.4, "end": 10.8, "word": " version"},
        {"start": 12.4, "end": 12.7, "word": " dangling"},
    ]

    kept = cut_word_transcript(edl, words)

    assert kept[0]["text"] == "real version"


# --- Workstream B: audio-truth silence removal ("mouth moving, no sound") ---


def test_silence_span_removed_when_word_free():
    """A word-free silent span between two phrases is collapsed to a micro-pause."""
    # words 0..9 then a 1.2s silent gap (no words) then words 10..19
    words = make_words(n=10, word_s=0.3, gap_s=0.1)
    gap_start = words[-1]["end"]
    tail = make_words(n=10, word_s=0.3, gap_s=0.1, start=gap_start + 1.2)
    all_words = words + tail
    silence = [{"start": gap_start, "end": gap_start + 1.2, "dur": 1.2}]
    d = EditDecisions()
    edl = compile_edl(
        d, all_words, "cam.mp4", total_dur(all_words), RENDER, GATES,
        tighten_gaps=False, silence_spans=silence,
    )
    # the silent span should be cut out -> two keep ranges around it
    removed = sum(b.start - a.end for a, b in zip(edl.ranges, edl.ranges[1:]))
    assert removed > 0.8  # most of the 1.2s silence gone
    # but a handle of silence remains on each side (not a zero-gap hard splice)
    assert removed < 1.2


def test_silence_removal_never_cuts_a_word():
    """A silence span that overlaps multiple normal word centers must not remove that phrase."""
    words = make_words(n=20, word_s=0.3, gap_s=0.1)
    # claim silence right over words 5..7 — must be ignored (overlaps speech)
    bad_span = [{"start": words[5]["start"], "end": words[7]["end"], "dur": 0.9}]
    d = EditDecisions()
    edl = compile_edl(
        d, words, "cam.mp4", total_dur(words), RENDER, GATES,
        tighten_gaps=False, silence_spans=bad_span,
    )
    # no word should fall inside a removed region: every word survives in some range
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        assert any(r.start <= mid <= r.end for r in edl.ranges), f"word at {mid} dropped"


def test_audio_truth_can_cut_single_stretched_whisper_word():
    """One overstretched token must not protect rendered silence from the hard QA gate."""
    words = [
        {"start": 0.0, "end": 1.3, "word": "before"},
        {"start": 1.3, "end": 2.8, "word": "stretched"},
        {"start": 2.9, "end": 4.2, "word": "after"},
    ]
    silence = [{"start": 1.5, "end": 2.6, "dur": 1.1}]
    edl = compile_edl(
        EditDecisions(), words, "cam.mp4", 4.6, RENDER, GATES,
        tighten_gaps=False, silence_spans=silence,
    )

    removed = sum(b.start - a.end for a, b in zip(edl.ranges, edl.ranges[1:]))
    assert removed > 0.75


def test_silence_inside_protected_moment_survives():
    """Deliberate silence inside a protected beat is NOT removed."""
    words = make_words(n=10, word_s=0.3, gap_s=0.1)
    gap_start = words[-1]["end"]
    tail = make_words(n=10, word_s=0.3, gap_s=0.1, start=gap_start + 1.2)
    all_words = words + tail
    silence = [{"start": gap_start, "end": gap_start + 1.2, "dur": 1.2}]
    # protect the silent beat wall-to-wall
    d = EditDecisions(protected_moments=[ProtectedMoment(start_s=gap_start - 0.1, end_s=gap_start + 1.3)])
    edl = compile_edl(
        d, all_words, "cam.mp4", total_dur(all_words), RENDER, GATES,
        tighten_gaps=False, silence_spans=silence,
    )
    removed = sum(b.start - a.end for a, b in zip(edl.ranges, edl.ranges[1:]))
    assert removed < 0.3  # protected silence preserved


# --- Workstream D: setup-payoff protection + scoped cold-open ---


def test_cold_open_prepends_payoff_clip():
    """A cold_open clip is rendered FIRST and also stays in the body (teaser + context)."""
    words = make_words(n=120, word_s=0.3, gap_s=0.1)
    # pick a payoff clip late in the video: words 100..108
    cs, ce = words[100]["start"], words[108]["end"]
    d = EditDecisions(cold_open={"start_s": cs, "end_s": ce, "reason": "the hook"})
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    # first range is the cold open, sourced from late in the timeline
    assert edl.ranges[0].beat == "COLD_OPEN"
    assert edl.ranges[0].start >= words[99]["end"]
    # the body still runs from the top (a later range starts near 0)
    assert any(r.start <= words[1]["start"] for r in edl.ranges[1:])
    # output order (cut transcript) stays monotonic despite the source reorder
    kept = cut_transcript(edl, [{"start": w["start"], "end": w["end"], "text": w["word"]} for w in words])
    outs = [p["out_start"] for p in kept]
    assert outs == sorted(outs)


def test_cold_open_capped_at_15s():
    words = make_words(n=200, word_s=0.3, gap_s=0.1)
    cs = words[100]["start"]
    ce = words[180]["end"]  # ~32s span, must be capped
    d = EditDecisions(cold_open={"start_s": cs, "end_s": ce})
    edl = compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES, tighten_gaps=False)
    cold = edl.ranges[0]
    assert cold.beat == "COLD_OPEN"
    assert cold.end - cold.start <= 15.5


def test_setup_protection_blocks_orphaning_cut():
    """A cut spanning a setup line is voided by the auto setup-protection."""
    from eddy.edit.protect import setup_protections
    phrases = [
        {"start": 0.0, "end": 2.0, "text": "intro words here we go"},
        {"start": 2.0, "end": 4.0, "text": "now let's look at the scripts"},
        {"start": 4.0, "end": 6.0, "text": "and here is the actual script content"},
    ]
    prot = setup_protections(phrases)
    assert any("scripts" in p.reason for p in prot)
    # the setup phrase 2.0-4.0 is protected
    assert any(p.start_s <= 3.0 <= p.end_s for p in prot)
