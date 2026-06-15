"""v0.3.1 speed-to-fit: duration math, speed-aware remap (captions/chapters stay synced),
eligibility safety rail, minimal-factor convergence, and back-compat."""

import json

from eddy.config import load_config
from eddy.edit.compiler import cut_transcript, src_to_out
from eddy.edit.schema import Edl, EddyMeta, EditDecisions, EdlRange, ProtectedMoment, load_edl
from eddy.loop.speed import _recompute_total, speed_to_fit


def cfg(**loop_over):
    c = load_config()
    c.loop.enable_speed_ramp = True
    c.loop.speed_ramp_max_multiplier = 1.4
    c.loop.speed_ramp_min_beat_s = 15.0
    c.loop.speed_ramp_max_wpm = 160.0
    for k, v in loop_over.items():
        setattr(c.loop, k, v)
    return c


def mk_edl(ranges):
    edl = Edl(sources={"camera": "x.mp4"}, ranges=ranges)
    edl.total_duration_s = _recompute_total(edl)
    return edl


# ---- duration math ------------------------------------------------------------------

def test_duration_halves_a_range_at_2x():
    edl = mk_edl([EdlRange(start=0, end=100, speed=2.0)])
    assert _recompute_total(edl) == 50.0


def test_mixed_speed_sum_is_exact():
    edl = mk_edl([EdlRange(start=0, end=60), EdlRange(start=100, end=160, speed=1.5)])
    assert _recompute_total(edl) == 100.0  # 60 + 40


# ---- speed-aware remap (the make-or-break correctness point) -------------------------

def test_remap_scales_inside_sped_beat_and_shifts_later_phrases_earlier():
    sped = mk_edl([EdlRange(start=0, end=10), EdlRange(start=10, end=20, speed=2.0)])
    flat = mk_edl([EdlRange(start=0, end=10), EdlRange(start=10, end=20)])
    phrases = [
        {"start": 2, "end": 4, "text": "in range one"},
        {"start": 12, "end": 14, "text": "in the 2x beat"},
    ]
    p2_sped = cut_transcript(sped, phrases)[1]
    p2_flat = cut_transcript(flat, phrases)[1]
    # within-segment: the 2s phrase compresses to 1s of output
    assert round(p2_sped["out_end"] - p2_sped["out_start"], 2) == 1.0
    # later phrase lands EARLIER than the un-sped edit (cursor advanced by span/speed)
    assert p2_sped["out_start"] == 11.0 and p2_flat["out_start"] == 12.0


def test_chapters_remap_agrees_with_cut_transcript():
    # src_to_out (chapters) must produce the same output time as cut_transcript for the same
    # source instant — they share the rule so captions and chapters can never drift apart.
    edl = mk_edl([EdlRange(start=0, end=10), EdlRange(start=10, end=20, speed=1.3)])
    phrase = [{"start": 13.0, "end": 15.0, "text": "x"}]
    out_start = cut_transcript(edl, phrase)[0]["out_start"]
    assert round(src_to_out(edl, 13.0), 2) == out_start
    assert out_start == 12.31  # independent literal: 10 + (13-10)/1.3 = 12.308


def test_remap_cursor_advance_divides_by_speed():
    # a sped range BEFORE the probed phrase: the cursor must advance by span/speed, not span.
    # This is the discriminating case — it FAILS (yields 12.0) if anyone drops /speed from the
    # cursor-advance line, locking down the highest-stakes invariant.
    edl = mk_edl([EdlRange(start=0, end=10, speed=2.0), EdlRange(start=10, end=20)])
    phrase = [{"start": 12, "end": 14, "text": "after the sped beat"}]
    out_start = cut_transcript(edl, phrase)[0]["out_start"]
    assert out_start == 7.0  # cursor after r0 = 10/2 = 5; within r1 offset 12-10 = 2 -> 7.0
    assert round(src_to_out(edl, 12.0), 2) == 7.0


# ---- eligibility safety rail ---------------------------------------------------------

def _eligibility_world():
    # each non-eligible beat is excluded by exactly ONE gate, so the test attributes the exclusion
    # to that gate (labels deliberately carry no hook/outro/payoff token except where intended).
    beats = [
        {"label": "Walkthrough", "start_s": 0, "end_s": 100},        # eligible
        {"label": "Speed Section", "start_s": 100, "end_s": 200},    # WPM gate only (240 wpm)
        {"label": "Quick Aside", "start_s": 200, "end_s": 300},      # SHORT gate only (10s)
        {"label": "Payoff Reveal", "start_s": 300, "end_s": 400},    # LABEL gate only (payoff/reveal)
        {"label": "Protected Section", "start_s": 400, "end_s": 500},  # PROTECTED gate only
    ]
    decisions = EditDecisions(
        x_eddy=EddyMeta(beats=beats),
        protected_moments=[ProtectedMoment(start_s=400, end_s=500, reason="demo")],
    )
    edl = mk_edl([
        EdlRange(start=0, end=100, beat="Walkthrough"),       # long + slow -> eligible
        EdlRange(start=100, end=200, beat="Speed Section"),   # fast wpm -> excluded
        EdlRange(start=200, end=210, beat="Quick Aside"),     # too short -> excluded
        EdlRange(start=300, end=400, beat="Payoff Reveal"),   # payoff label -> excluded
        EdlRange(start=400, end=500, beat="Protected Section"),  # protected overlap -> excluded
    ])
    beat_density = [
        {"label": "Walkthrough", "kept_s": 100, "wpm": 120},
        {"label": "Speed Section", "kept_s": 100, "wpm": 240},   # only the wpm gate stops this
        {"label": "Quick Aside", "kept_s": 10, "wpm": 120},      # only the min-beat gate stops this
        {"label": "Payoff Reveal", "kept_s": 100, "wpm": 120},   # only the label gate stops this
        {"label": "Protected Section", "kept_s": 100, "wpm": 120},  # only protected overlap stops this
    ]
    return edl, decisions, beat_density


def test_only_long_slow_unprotected_beats_are_sped():
    edl, decisions, bd = _eligibility_world()
    info = speed_to_fit(edl, decisions, bd, cfg(length_ceiling_minutes=1.0))  # ceiling 60s, way under 410
    assert edl.ranges[0].speed > 1.0          # Walkthrough sped
    assert all(r.speed == 1.0 for r in edl.ranges[1:])  # everything else untouched
    assert [b["label"] for b in info["beats_sped"]] == ["Walkthrough"]
    assert edl.ranges[0].speed == 1.4         # huge gap -> capped


def test_residual_gap_is_reported_not_forced():
    edl, decisions, bd = _eligibility_world()
    info = speed_to_fit(edl, decisions, bd, cfg(length_ceiling_minutes=1.0))
    # only one eligible beat at 1.4x cannot close a 350s gap -> ship best-effort, log the shortfall
    assert info["ceiling_missed_s"] > 0
    assert info["applied"] is True


# ---- minimal factor + cap ------------------------------------------------------------

def test_factor_is_minimal_and_under_cap():
    decisions = EditDecisions(x_eddy=EddyMeta(beats=[{"label": "Walkthrough", "start_s": 0, "end_s": 100}]))
    edl = mk_edl([EdlRange(start=0, end=100, beat="Walkthrough")])
    bd = [{"label": "Walkthrough", "kept_s": 100, "wpm": 120}]
    info = speed_to_fit(edl, decisions, bd, cfg(length_ceiling_minutes=90 / 60))  # ceiling 90s, over 10s
    assert edl.ranges[0].speed == 1.111      # 100/(100-10), minimal — not the 1.4 cap
    assert abs(edl.total_duration_s - 90.0) < 0.2
    assert info["ceiling_missed_s"] == 0.0


def test_disabled_is_a_noop():
    decisions = EditDecisions(x_eddy=EddyMeta(beats=[{"label": "Walkthrough", "start_s": 0, "end_s": 100}]))
    edl = mk_edl([EdlRange(start=0, end=100, beat="Walkthrough")])
    bd = [{"label": "Walkthrough", "kept_s": 100, "wpm": 120}]
    c = cfg(length_ceiling_minutes=1.0)
    c.loop.enable_speed_ramp = False
    info = speed_to_fit(edl, decisions, bd, c)
    assert edl.ranges[0].speed == 1.0 and info["applied"] is False


def test_under_ceiling_is_a_noop():
    decisions = EditDecisions(x_eddy=EddyMeta(beats=[{"label": "Walkthrough", "start_s": 0, "end_s": 100}]))
    edl = mk_edl([EdlRange(start=0, end=100, beat="Walkthrough")])
    bd = [{"label": "Walkthrough", "kept_s": 100, "wpm": 120}]
    info = speed_to_fit(edl, decisions, bd, cfg(length_ceiling_minutes=10.0))  # ceiling 600s >> 100s
    assert edl.ranges[0].speed == 1.0 and info["applied"] is False


def test_non_clean_cap_does_not_crash_and_respects_cap():
    # a non-round cap could, after 3dp rounding, exceed itself and trip the invariant assert.
    decisions = EditDecisions(x_eddy=EddyMeta(beats=[{"label": "Walkthrough", "start_s": 0, "end_s": 100}]))
    edl = mk_edl([EdlRange(start=0, end=100, beat="Walkthrough")])
    bd = [{"label": "Walkthrough", "kept_s": 100, "wpm": 120}]
    info = speed_to_fit(edl, decisions, bd, cfg(length_ceiling_minutes=1.0, speed_ramp_max_multiplier=1.41666))
    assert info["applied"] is True
    assert all((r.speed or 1.0) <= 1.41666 + 1e-6 for r in edl.ranges)


def test_duplicate_labels_each_keep_their_own_span():
    # the collapse bug kept only the LAST same-label span, leaving earlier same-label beats un-sped.
    beats = [{"label": "Story", "start_s": 0, "end_s": 100}, {"label": "Story", "start_s": 100, "end_s": 200}]
    decisions = EditDecisions(x_eddy=EddyMeta(beats=beats))
    edl = mk_edl([EdlRange(start=0, end=100, beat="Story"), EdlRange(start=100, end=200, beat="Story")])
    bd = [{"label": "Story", "kept_s": 100, "wpm": 120}, {"label": "Story", "kept_s": 100, "wpm": 120}]
    speed_to_fit(edl, decisions, bd, cfg(length_ceiling_minutes=1.0))  # ceiling 60s, over 140s
    assert edl.ranges[0].speed > 1.0 and edl.ranges[1].speed > 1.0  # BOTH sped, not just the last


# ---- back-compat ---------------------------------------------------------------------

def test_old_edl_without_speed_field_loads_as_1x(tmp_path):
    raw = {"version": 1, "sources": {"camera": "x.mp4"},
           "ranges": [{"start": 0, "end": 100}], "total_duration_s": 100.0}
    path = tmp_path / "edl.json"
    path.write_text(json.dumps(raw))
    edl = load_edl(path)
    assert edl.ranges[0].speed == 1.0
    assert _recompute_total(edl) == 100.0


# ---- real render regression (catches the output-side -t bug the in-memory tests cannot) ----

def test_render_sped_edl_passes_av_drift(tmp_path):
    """A real ffmpeg render of a mixed-speed EDL must land within the av_drift tolerance — i.e.
    setpts/atempo actually compress the segment and the EDL duration is physically producible.
    The in-memory tests above never render, so only this catches an output-side -t regression."""
    import shutil
    import subprocess

    import pytest

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe not available")
    from eddy.qa.deterministic import av_drift
    from eddy.render.segments import render_edl

    src = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=40",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)],
        check=True,
    )
    edl = Edl(sources={"camera": str(src)}, ranges=[
        EdlRange(start=2, end=12, speed=1.0),    # 10.0s
        EdlRange(start=15, end=35, speed=1.4),   # 20/1.4 = 14.286s
    ])
    edl.total_duration_s = _recompute_total(edl)  # 24.286
    out = tmp_path / "out.mp4"
    c = load_config()
    render_edl(edl, out, tmp_path, c.render, proxy=True)  # libx264, portable
    gate = av_drift(out, edl, c.gates.max_av_drift_s)
    assert gate["pass"], gate
