"""simulate() sim-report fields + post-cut beat_density on synthetic EDLs.

raw_beat_density is covered in test_aggressive_cut.py — this targets simulate()
itself: duration/ranges/removed_total_s/boundary_cards, the three verdicts and
pass, dead-air detection (and protected-moment exemption), thin-handle gating,
and the kept-phrase beat_density (heaviest-first + wpm).
"""

from eddy.config import EddyConfig
from eddy.edit.schema import EddyMeta, EditDecisions, Edl, EdlRange, ProtectedMoment
from eddy.edit.simulate import simulate

CFG = EddyConfig()
TARGET_S = 600.0


def mk_edl(ranges):
    edl = Edl(sources={"camera": "cam.mp4"}, ranges=ranges)
    edl.total_duration_s = round(sum(r.end - r.start for r in ranges), 2)
    return edl


def phrase(start, end, text):
    return {"start": start, "end": end, "text": text}


def test_single_range_no_splice_passes_clean():
    # one keep range, no cut between ranges -> nothing removed, no cards, clean pass
    edl = mk_edl([EdlRange(start=0.0, end=10.0, start_handle_s=0.2, end_handle_s=0.2)])
    phrases = [phrase(1.0, 2.0, "hello there"), phrase(3.0, 4.0, "world now")]
    d = EditDecisions()
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    assert rep["duration_s"] == 10.0
    assert rep["ranges"] == 1
    assert rep["removed_total_s"] == 0.0
    assert rep["boundary_cards"] == []
    assert rep["kept_phrases"] == 2
    assert rep["pass"] is True
    assert rep["verdicts"] == {"no_dead_air": True, "handles_safe": True, "has_content": True}


def test_two_ranges_emit_one_boundary_card_and_removed_total():
    # 10s kept, 4s cut, 10s kept -> exactly one splice card, removed_total_s == 4.0
    edl = mk_edl([
        EdlRange(start=0.0, end=10.0, start_handle_s=0.2, end_handle_s=0.2),
        EdlRange(start=14.0, end=24.0, start_handle_s=0.2, end_handle_s=0.2),
    ])
    phrases = [
        phrase(8.0, 9.0, "last kept before cut"),
        phrase(11.0, 12.0, "removed middle words"),
        phrase(15.0, 16.0, "first kept after cut"),
    ]
    d = EditDecisions()
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    assert rep["ranges"] == 2
    assert rep["removed_total_s"] == 4.0
    assert len(rep["boundary_cards"]) == 1
    card = rep["boundary_cards"][0]
    assert card["splice_at_source_s"] == 10.0
    assert card["removed_s"] == 4.0
    # the removed phrase sits in the gap; the kept neighbours frame it
    assert "removed middle words" in card["removed_summary"]
    assert "last kept before cut" in card["before_text"]
    assert "first kept after cut" in card["after_text"]


def test_has_content_false_when_no_phrase_survives():
    # phrases all land OUTSIDE the keep range (midpoint not contained) -> empty cut transcript
    edl = mk_edl([EdlRange(start=100.0, end=110.0, start_handle_s=0.2, end_handle_s=0.2)])
    phrases = [phrase(1.0, 2.0, "way before the range")]
    d = EditDecisions()
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    assert rep["kept_phrases"] == 0
    assert rep["verdicts"]["has_content"] is False
    assert rep["pass"] is False


def test_dead_air_inside_output_fails_no_dead_air_verdict():
    # one keep range, but a >1.5s output gap between two surviving phrases (no protection)
    edl = mk_edl([EdlRange(start=0.0, end=20.0, start_handle_s=0.2, end_handle_s=0.2)])
    phrases = [phrase(1.0, 2.0, "before the silence"), phrase(8.0, 9.0, "after the silence")]
    d = EditDecisions()
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    # output gap = out_start(after=8.0) - out_end(before=2.0) = 6.0 > max_dead_air_s(1.5)
    assert len(rep["dead_air"]) == 1
    assert rep["dead_air"][0]["gap_s"] == 6.0
    assert rep["verdicts"]["no_dead_air"] is False
    assert rep["pass"] is False


def test_protected_moment_exempts_dead_air():
    # same dead-air gap, but the phrase before it is inside a protected moment -> exempt, passes
    edl = mk_edl([EdlRange(start=0.0, end=20.0, start_handle_s=0.2, end_handle_s=0.2)])
    phrases = [phrase(1.0, 2.0, "before the silence"), phrase(8.0, 9.0, "after the silence")]
    # the phrase before the gap ends at raw 2.0; protect that span
    d = EditDecisions(protected_moments=[ProtectedMoment(start_s=1.5, end_s=2.5, reason="demo beat")])
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    assert rep["dead_air"] == []
    assert rep["verdicts"]["no_dead_air"] is True
    assert rep["pass"] is True


def test_thin_handle_fails_handles_safe_verdict():
    # the second range opens with a sub-30ms (0.02s) handle -> hard fail on handles_safe
    edl = mk_edl([
        EdlRange(start=0.0, end=10.0, start_handle_s=0.2, end_handle_s=0.2),
        EdlRange(start=14.0, end=24.0, start_handle_s=0.02, end_handle_s=0.2),
    ])
    phrases = [phrase(5.0, 6.0, "kept one"), phrase(18.0, 19.0, "kept two")]
    d = EditDecisions()
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    assert len(rep["thin_handles"]) == 1
    assert rep["verdicts"]["handles_safe"] is False
    assert rep["pass"] is False


def test_handle_between_fade_floor_and_min_is_a_warning_not_a_fail():
    # 0.05s handle is >= FADE_FLOOR (0.03) but < min_boundary_handle_s (0.10):
    # reported as a handle_warning, NOT a thin_handle, and does not fail the gate
    edl = mk_edl([
        EdlRange(start=0.0, end=10.0, start_handle_s=0.2, end_handle_s=0.2),
        EdlRange(start=14.0, end=24.0, start_handle_s=0.05, end_handle_s=0.2),
    ])
    # phrases adjacent across the splice in OUTPUT time so no dead-air masks the handle result:
    # out_end(first)=9.5, out_start(second)=10.0 -> 0.5s gap < max_dead_air_s
    phrases = [phrase(9.0, 9.5, "kept one"), phrase(14.0, 15.0, "kept two")]
    d = EditDecisions()
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    assert rep["thin_handles"] == []
    assert rep["handle_warnings"] == 1
    assert rep["verdicts"]["handles_safe"] is True
    assert rep["verdicts"]["no_dead_air"] is True
    assert rep["pass"] is True


def test_beat_density_heaviest_first_with_wpm():
    # two beats: a long, kept-heavy WALKTHROUGH and a short HOOK -> WALKTHROUGH ranks first
    edl = mk_edl([EdlRange(start=0.0, end=40.0, start_handle_s=0.2, end_handle_s=0.2)])
    # HOOK beat 0..10s: one 1s phrase, 2 words -> kept_s ~= 1.0, wpm = 2/1*60 = 120
    # WALK beat 10..40s: three 2s phrases each 3 words -> kept_s ~= 6.0, 9 words -> 90 wpm
    phrases = [
        phrase(2.0, 3.0, "two words"),
        phrase(12.0, 14.0, "reading the screen"),
        phrase(20.0, 22.0, "reading the screen"),
        phrase(30.0, 32.0, "reading the screen"),
    ]
    d = EditDecisions(
        x_eddy=EddyMeta(beats=[
            {"label": "HOOK", "start_s": 0.0, "end_s": 10.0},
            {"label": "WALKTHROUGH", "start_s": 10.0, "end_s": 40.0},
        ])
    )
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    bd = rep["beat_density"]
    assert [b["label"] for b in bd] == ["WALKTHROUGH", "HOOK"]
    walk = bd[0]
    assert walk["kept_s"] == 6.0
    assert walk["wpm"] == 90.0  # 9 words / 6s * 60
    hook = bd[1]
    assert hook["kept_s"] == 1.0
    assert hook["wpm"] == 120.0  # 2 words / 1s * 60


def test_beat_with_no_kept_phrases_is_omitted_from_density():
    # an EMPTY beat (no phrase midpoints inside it) must not appear in beat_density
    edl = mk_edl([EdlRange(start=0.0, end=40.0, start_handle_s=0.2, end_handle_s=0.2)])
    phrases = [phrase(2.0, 3.0, "only in the first beat")]
    d = EditDecisions(
        x_eddy=EddyMeta(beats=[
            {"label": "HOOK", "start_s": 0.0, "end_s": 10.0},
            {"label": "EMPTY", "start_s": 10.0, "end_s": 40.0},
        ])
    )
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    labels = [b["label"] for b in rep["beat_density"]]
    assert "EMPTY" not in labels
    assert labels == ["HOOK"]


def test_cold_open_splice_is_not_a_boundary_card():
    # a COLD_OPEN reorder (right.start < left.start) is a deliberate hard cut, not a splice:
    # it must NOT produce a boundary card, and the source-order splice after it still does
    edl = mk_edl([
        EdlRange(start=30.0, end=40.0, beat="COLD_OPEN", start_handle_s=0.2, end_handle_s=0.2),
        EdlRange(start=0.0, end=10.0, start_handle_s=0.2, end_handle_s=0.2),
        EdlRange(start=14.0, end=24.0, start_handle_s=0.2, end_handle_s=0.2),
    ])
    phrases = [
        phrase(35.0, 36.0, "cold open payoff"),
        phrase(5.0, 6.0, "body start"),
        phrase(18.0, 19.0, "body continues"),
    ]
    d = EditDecisions()
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    # 3 ranges -> 2 adjacent pairs, but the cold-open->body pair is a reorder (skipped)
    assert rep["ranges"] == 3
    assert len(rep["boundary_cards"]) == 1
    assert rep["boundary_cards"][0]["splice_at_source_s"] == 10.0


def test_band_and_ceiling_reported_from_config():
    edl = mk_edl([EdlRange(start=0.0, end=300.0, start_handle_s=0.2, end_handle_s=0.2)])
    phrases = [phrase(1.0, 2.0, "content here")]
    d = EditDecisions()
    rep = simulate(edl, d, phrases, CFG, TARGET_S)

    lo, hi = CFG.loop.duration_band
    assert rep["target_s"] == TARGET_S
    assert rep["band_s"] == [round(lo * TARGET_S, 1), round(hi * TARGET_S, 1)]
    assert rep["ceiling_s"] == round(CFG.loop.length_ceiling_minutes * 60, 1)
    # 300s duration is under the 14min (840s) ceiling
    assert rep["under_ceiling"] is True
