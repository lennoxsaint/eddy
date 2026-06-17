"""v1.6 extract continuity: the deterministic bridge-merge turns the many small keep ranges a
topical extract produces into a few contiguous blocks (so explanations aren't severed mid-thought),
drops orphan slivers, snaps edges to phrase boundaries — and a NON-extract edit is left untouched."""

from eddy.config import GatesConfig, RenderConfig
from eddy.edit.compiler import _bridge_keep_gaps, _snap_out_to_phrase, compile_edl
from eddy.edit.schema import Cut, EditDecisions, EdlRange

GATES = GatesConfig()
RENDER = RenderConfig()


def _ranges(*pairs):
    return [EdlRange(start=s, end=e) for s, e in pairs]


def _make_words(*, n=100, word_s=0.3, gap_s=0.1):
    words, t = [], 0.0
    for i in range(n):
        words.append({"start": round(t, 3), "end": round(t + word_s, 3), "word": f" w{i}", "probability": 0.9})
        t += word_s + gap_s
    return words


# --- bridge-merge geometry --------------------------------------------------------------------

def test_bridges_small_gaps_keeps_large_gaps_and_drops_slivers():
    # gaps: 0.5, 4.0, 0.3 (all <=6 -> bridge); 12.0 (>6 -> stay cut); trailing 1.5s block is a sliver
    rs = _ranges((0, 3), (3.5, 6), (10, 13), (25, 27), (27.3, 28), (40, 41.5))
    out = _bridge_keep_gaps(rs, [], GATES, duration_s=60.0)
    spans = [(r.start, r.end) for r in out]
    assert spans == [(0.0, 13.0), (25.0, 28.0)]  # 6 fragments -> 2 contiguous blocks, sliver dropped


def test_gap_exactly_at_threshold_bridges():
    rs = _ranges((0, 3), (9, 12))  # gap == 6.0 == extract_bridge_gap_s -> bridge (<=)
    out = _bridge_keep_gaps(rs, [], GATES, duration_s=60.0)
    assert [(r.start, r.end) for r in out] == [(0.0, 12.0)]


def test_gap_just_over_threshold_stays_separate():
    rs = _ranges((0, 3), (9.1, 12))  # gap 6.1 > 6.0 -> stay separate
    out = _bridge_keep_gaps(rs, [], GATES, duration_s=60.0)
    assert len(out) == 2


def test_isolated_sliver_is_dropped_but_short_block_adjacent_survives_via_bridge():
    # a lone 1.5s block is debris; but a 1.5s block within bridge range of a big one is absorbed
    dropped = _bridge_keep_gaps(_ranges((40, 41.5)), [], GATES, duration_s=60.0)
    assert dropped == []
    absorbed = _bridge_keep_gaps(_ranges((0, 10), (11, 12.5)), [], GATES, duration_s=60.0)
    assert [(r.start, r.end) for r in absorbed] == [(0.0, 12.5)]


def test_empty_and_single_range():
    assert _bridge_keep_gaps([], [], GATES, 60.0) == []
    one = _bridge_keep_gaps(_ranges((0, 5)), [], GATES, 60.0)
    assert [(r.start, r.end) for r in one] == [(5.0 - 5.0, 5.0)]


# --- phrase-boundary snapping -----------------------------------------------------------------

def test_phrase_snap_grows_block_out_to_sentence_edges_within_window():
    phrases = [{"start": 4.6, "end": 5.4, "text": "a"}, {"start": 8.7, "end": 9.3, "text": "b"}]
    out = _bridge_keep_gaps(_ranges((5.0, 9.0)), phrases, GATES, duration_s=60.0)
    r = out[0]
    assert r.start == 4.6 and r.end == 9.3  # snapped out to phrase boundaries (0.4s / 0.3s, within 1.5s)
    assert r.start_handle_s == 0.0 and r.end_handle_s == 0.0  # boundary now sits on a phrase edge


def test_phrase_snap_respects_window():
    # phrase starts 3.0s before the edge — beyond the 1.5s window — so no snap
    assert _snap_out_to_phrase(5.0, [{"start": 2.0, "end": 5.4, "text": "x"}], 1.5, None, "start") == 5.0


def test_phrase_snap_never_crosses_neighbour_bound():
    # bound (a neighbour block edge) caps the outward move
    snapped = _snap_out_to_phrase(9.0, [{"start": 8.7, "end": 9.3, "text": "b"}], 1.5, 9.1, "end")
    assert snapped == 9.1


# --- integration through compile_edl ----------------------------------------------------------

def _decisions_with_three_cuts(words):
    return EditDecisions(cuts=[
        Cut(start_s=words[10]["start"], end_s=words[12]["end"], tier="MANDATORY"),
        Cut(start_s=words[25]["start"], end_s=words[27]["end"], tier="MANDATORY"),
        Cut(start_s=words[45]["start"], end_s=words[47]["end"], tier="MANDATORY"),
    ])


def test_extract_collapses_fragments_normal_edit_unchanged():
    words = _make_words()
    dur = words[-1]["end"] + 1.0
    d_normal = _decisions_with_three_cuts(words)
    d_extract = _decisions_with_three_cuts(words)

    normal = compile_edl(d_normal, words, "cam.mp4", dur, RENDER, GATES, tighten_gaps=False)
    extract = compile_edl(
        d_extract, words, "cam.mp4", dur, RENDER, GATES, tighten_gaps=False, phrases=[], extract=True
    )
    # three short cuts split the timeline into four small keeps; the bridge-merge fuses them (all
    # inter-keep gaps are ~1s, well under 6s) into one contiguous block.
    assert len(normal.ranges) == 4
    assert len(extract.ranges) == 1


def test_extract_false_is_identical_to_default():
    words = _make_words()
    dur = words[-1]["end"] + 1.0
    base = compile_edl(_decisions_with_three_cuts(words), words, "cam.mp4", dur, RENDER, GATES, tighten_gaps=False)
    explicit = compile_edl(
        _decisions_with_three_cuts(words), words, "cam.mp4", dur, RENDER, GATES,
        tighten_gaps=False, phrases=[], extract=False,
    )
    assert [(r.start, r.end) for r in base.ranges] == [(r.start, r.end) for r in explicit.ranges]
