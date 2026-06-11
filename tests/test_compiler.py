"""Compiler invariants on synthetic transcripts."""

import pytest

from eddy.config import GatesConfig, RenderConfig
from eddy.edit.compiler import CompileError, compile_edl, cut_transcript, gap_tighten_intervals
from eddy.edit.schema import Cut, EditDecisions, ProtectedMoment, Retake

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


def test_protected_moment_substantial_cut_raises():
    words = make_words()
    # cut removes the protected span entirely (overlap > 25% of span)
    d = EditDecisions(
        cuts=[Cut(start_s=words[10]["start"], end_s=words[20]["end"], tier="MANDATORY")],
        protected_moments=[ProtectedMoment(start_s=words[15]["start"], end_s=words[18]["end"])],
    )
    with pytest.raises(CompileError) as e:
        compile_edl(d, words, "cam.mp4", total_dur(words), RENDER, GATES)
    assert e.value.problems[0]["type"] == "protected_moment_cut"


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
    assert s >= words[4]["end"] + 0.2
    assert e <= words[5]["start"] - 0.2


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
