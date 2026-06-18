"""v1.6 extract continuity. Two layers, tested where each lives:
- REMOVE-LEVEL bridge (v1.6.3): in compile_edl(extract=True) the small CUT gaps that chop one
  explanation into slivers are dropped (re-admitted) so the on-topic keeps join, while large
  off-topic cuts and retakes stay; the silence inside a re-admitted bridge is still cut.
- POST-INVERSION finalize (_finalize_extract_blocks): phrase-boundary snap + sliver-drop.
A non-extract edit enters neither path and is byte-identical."""

from eddy.config import GatesConfig, RenderConfig
from eddy.edit.compiler import _finalize_extract_blocks, _snap_out_to_phrase, compile_edl
from eddy.edit.schema import Cut, EditDecisions, EdlRange, Retake

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


# --- post-inversion finalize: sliver-drop ------------------------------------------------------

def test_finalize_drops_isolated_slivers():
    out = _finalize_extract_blocks(_ranges((0, 10), (20, 21.5)), [], GATES, duration_s=60.0)
    assert [(r.start, r.end) for r in out] == [(0.0, 10.0)]  # the lone 1.5s block is debris


def test_finalize_keeps_blocks_at_or_above_min():
    out = _finalize_extract_blocks(_ranges((0, 10), (20, 23)), [], GATES, duration_s=60.0)
    assert len(out) == 2  # 3.0s >= extract_min_block_s (2.5)


def test_finalize_empty_and_single():
    assert _finalize_extract_blocks([], [], GATES, 60.0) == []
    one = _finalize_extract_blocks(_ranges((0, 5)), [], GATES, 60.0)
    assert [(r.start, r.end) for r in one] == [(0.0, 5.0)]


# --- phrase-boundary snapping -----------------------------------------------------------------

def test_phrase_snap_grows_block_out_to_sentence_edges_within_window():
    phrases = [{"start": 4.6, "end": 5.4, "text": "a"}, {"start": 8.7, "end": 9.3, "text": "b"}]
    out = _finalize_extract_blocks(_ranges((5.0, 9.0)), phrases, GATES, duration_s=60.0)
    r = out[0]
    assert r.start == 4.6 and r.end == 9.3  # snapped out to phrase boundaries (0.4s / 0.3s, within 1.5s)
    assert r.start_handle_s == 0.0 and r.end_handle_s == 0.0  # boundary now sits on a phrase edge


def test_phrase_snap_respects_window():
    # phrase starts 3.0s before the edge — beyond the 1.5s window — so no snap
    assert _snap_out_to_phrase(5.0, [{"start": 2.0, "end": 5.4, "text": "x"}], 1.5, None, "start") == 5.0


def test_phrase_snap_never_crosses_neighbour_bound():
    snapped = _snap_out_to_phrase(9.0, [{"start": 8.7, "end": 9.3, "text": "b"}], 1.5, 9.1, "end")
    assert snapped == 9.1


# --- remove-level bridging through compile_edl -------------------------------------------------

def _three_small_cuts(words):
    return EditDecisions(cuts=[
        Cut(start_s=words[10]["start"], end_s=words[12]["end"], tier="MANDATORY"),
        Cut(start_s=words[25]["start"], end_s=words[27]["end"], tier="MANDATORY"),
        Cut(start_s=words[45]["start"], end_s=words[47]["end"], tier="MANDATORY"),
    ])


def test_extract_collapses_small_cut_fragments_normal_edit_unchanged():
    words = _make_words()
    dur = words[-1]["end"] + 1.0
    normal = compile_edl(_three_small_cuts(words), words, "c.mp4", dur, RENDER, GATES, tighten_gaps=False)
    extract = compile_edl(
        _three_small_cuts(words), words, "c.mp4", dur, RENDER, GATES, tighten_gaps=False, phrases=[], extract=True
    )
    assert len(normal.ranges) == 4   # three small cuts -> four keeps
    assert len(extract.ranges) == 1  # all three small cuts bridged away -> one contiguous block


def test_extract_bridges_small_cuts_keeps_large_off_topic_cut():
    words = _make_words()
    dur = words[-1]["end"] + 1.0
    cuts = [
        Cut(start_s=words[10]["start"], end_s=words[12]["end"], tier="MANDATORY"),   # ~1.1s small -> bridged
        Cut(start_s=words[30]["start"], end_s=words[70]["end"], tier="MANDATORY"),   # ~16s large  -> kept
    ]
    normal = compile_edl(EditDecisions(cuts=list(cuts)), words, "c.mp4", dur, RENDER, GATES, tighten_gaps=False)
    extract = compile_edl(
        EditDecisions(cuts=list(cuts)), words, "c.mp4", dur, RENDER, GATES, tighten_gaps=False, phrases=[], extract=True
    )
    assert len(normal.ranges) == 3
    assert len(extract.ranges) == 2  # small cut bridged; large off-topic cut remains


def test_extract_does_not_bridge_a_retake():
    # a retake removal (a duplicate take) is never bridged, even when short
    words = _make_words()
    dur = words[-1]["end"] + 1.0
    d = EditDecisions(retakes=[Retake(remove_start_s=words[10]["start"], remove_end_s=words[12]["end"], kept_take="last")])
    extract = compile_edl(d, words, "c.mp4", dur, RENDER, GATES, tighten_gaps=False, phrases=[], extract=True)
    assert len(extract.ranges) == 2  # the retake gap is preserved (not re-admitted)


def test_extract_false_is_identical_to_default():
    words = _make_words()
    dur = words[-1]["end"] + 1.0
    base = compile_edl(_three_small_cuts(words), words, "c.mp4", dur, RENDER, GATES, tighten_gaps=False)
    explicit = compile_edl(
        _three_small_cuts(words), words, "c.mp4", dur, RENDER, GATES, tighten_gaps=False, phrases=[], extract=False
    )
    assert [(r.start, r.end) for r in base.ranges] == [(r.start, r.end) for r in explicit.ranges]
