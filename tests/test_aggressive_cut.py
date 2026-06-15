"""v0.3.2 aggressive cut: feasibility-gated plateau, protection-budget enforcement, raw beat
density, directive escalation, and the deterministic trim-to-fit backstop's selection + revert."""

import json

from eddy.config import load_config
from eddy.edit.protect import enforce_protection_budget
from eddy.edit.schema import Edl, EddyMeta, EditDecisions, EdlRange, ProtectedMoment
from eddy.edit.simulate import raw_beat_density
from eddy.loop.controller import _directive_from, _made_progress, _plateau_step
from eddy.loop.state import RunState
from eddy.loop.trim import _recompute_total, _removable_beats, trim_to_fit


def cfg(**loop_over):
    c = load_config()
    for k, v in loop_over.items():
        setattr(c.loop, k, v)
    return c


def mk_edl(ranges):
    edl = Edl(sources={"camera": "x.mp4"}, ranges=ranges)
    edl.total_duration_s = _recompute_total(ranges)
    return edl


# ---- feasibility-gated plateau ------------------------------------------------------

def test_flat_quality_but_still_cutting_is_progress():
    # quality unchanged, but this round cut materially closer to the ceiling while still over it
    loop = cfg().loop  # ceiling_tolerance_s=5, min_length_progress_s=5
    assert _made_progress(5.0, 5.0, over_ceiling_s=900.0, best_over=1000.0, loop=loop) is True


def test_both_flat_is_a_plateau():
    loop = cfg().loop
    # quality flat AND duration didn't drop (over == best_over) -> no progress -> plateau will fire
    assert _made_progress(5.0, 5.0, over_ceiling_s=1000.0, best_over=1000.0, loop=loop) is False


def test_within_tolerance_stops_even_if_nominally_closer():
    loop = cfg().loop
    # already within ceiling_tolerance_s of the ceiling: length axis is "done", quality flat -> stop
    assert _made_progress(5.0, 5.0, over_ceiling_s=3.0, best_over=50.0, loop=loop) is False


def test_tiny_length_drop_is_not_progress():
    loop = cfg().loop
    # dropped only 2s (< min_length_progress_s=5) -> not progress on the length axis
    assert _made_progress(5.0, 5.0, over_ceiling_s=998.0, best_over=1000.0, loop=loop) is False


def test_quality_improvement_is_always_progress():
    loop = cfg().loop
    # quality climbed -> progress regardless of length
    assert _made_progress(6.0, 5.0, over_ceiling_s=1000.0, best_over=1000.0, loop=loop) is True


def test_made_progress_boundary_is_strict():
    loop = cfg().loop  # ceiling_tolerance_s=5, min_length_progress_s=5
    # exactly at the progress threshold (over == best_over - min_length_progress_s) is NOT progress
    assert _made_progress(5.0, 5.0, over_ceiling_s=995.0, best_over=1000.0, loop=loop) is False
    # exactly at the tolerance edge (over == ceiling_tolerance_s) is NOT over-ceiling enough
    assert _made_progress(5.0, 5.0, over_ceiling_s=5.0, best_over=1000.0, loop=loop) is False


# ---- feasibility-gated plateau WIRING (the actual fix; order is load-bearing) --------

def _run_plateau(seq, loop):
    """Mirror edit_loop's exact update order: best_over starts at the 1e9 sentinel; each round calls
    _plateau_step then folds best_over in. Returns the 1-based round it stops at, or None."""
    no_improve, prev_best_q, best_over = 0, -1.0, 1e9
    for i, (q, over) in enumerate(seq, 1):
        no_improve, prev_best_q, best_over, stop = _plateau_step(
            no_improve, prev_best_q, best_over, q, over, loop)
        if stop:
            return i
    return None


def test_plateau_keeps_cutting_on_flat_quality():
    # the v0.3 floor regression: flat quality, duration steadily dropping, still way over ceiling.
    # v0.3 stopped here after 2 rounds; v0.3.2 must keep going (length is the second axis).
    loop = cfg(plateau_rounds=2).loop
    seq = [(4.0, 1500.0), (4.0, 1400.0), (4.0, 1300.0), (4.0, 1200.0), (4.0, 1100.0)]
    assert _run_plateau(seq, loop) is None


def test_plateau_bootstrap_first_over_ceiling_cut_counts():
    # the 1e9 sentinel + pre-update best_over order must let the FIRST over-ceiling round count as
    # length progress even when quality is FLAT. Moving the best_over update before the
    # _made_progress call makes len_improved (1500 < 1500-5) false and would increment no_improve.
    loop = cfg(plateau_rounds=2).loop
    no_improve, _, best_over, stop = _plateau_step(0, 4.0, 1e9, 4.0, 1500.0, loop)  # prev_q==cur_q (flat)
    assert no_improve == 0 and best_over == 1500.0 and stop is False


def test_plateau_stops_when_both_quality_and_length_stall():
    loop = cfg(plateau_rounds=2).loop
    # cut for one round, then duration stalls with flat quality -> plateau after plateau_rounds stalls
    seq = [(4.0, 1500.0), (4.0, 1400.0), (4.0, 1400.0), (4.0, 1400.0)]
    assert _run_plateau(seq, loop) == 4


# ---- best_over persistence (resume correctness) -------------------------------------

def test_set_plateau_persists_best_over(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.set_plateau(2, 7.3, best_over=120.0)
    assert RunState(tmp_path / "r").data["best_over"] == 120.0
    # omitting best_over must NOT overwrite the stored value to None
    s.set_plateau(3, 7.5)
    assert "best_over" not in RunState(tmp_path / "r").data or RunState(tmp_path / "r").data["best_over"] == 120.0


# ---- compile_with_repair re-enforces the budget on the repair path (major fix) ------

def test_protection_budget_reenforced_on_repair_path(tmp_path, monkeypatch):
    """The repair loop rebuilds protected_moments from raw model output; the budget must be
    re-applied on every compile attempt, not just the first, or over-broad protections sneak back."""
    import eddy.edit.cutplan as cp
    from eddy.edit.compiler import CompileError

    big = ProtectedMoment(start_s=100, end_s=700)  # 600s, way over a 200s budget (0.2 * 1000)
    d = EditDecisions(retakes=[], cuts=[], protected_moments=[big, ProtectedMoment(start_s=0, end_s=10)],
                      shorts_candidates=[])
    d.x_eddy = EddyMeta(iteration=1, beats=[])

    monkeypatch.setattr(cp, "manifest", lambda rd: {"sources": {"camera": "x.mp4"}})
    monkeypatch.setattr(cp, "words_flat", lambda rd: [])
    monkeypatch.setattr(cp, "probe_duration", lambda p: 1000.0)
    monkeypatch.setattr(cp, "audio_silence_map", lambda rd: [])
    monkeypatch.setattr(cp, "load_phrases", lambda rd: [])
    monkeypatch.setattr(cp, "setup_protections", lambda ph: [])

    # revise_decisions (the repair) returns decisions with the 600s protection RE-EXPANDED
    def fake_revise(rd, prov, rec, prev, directive, it):
        nd = EditDecisions(retakes=[], cuts=[], protected_moments=[ProtectedMoment(start_s=100, end_s=700)],
                           shorts_candidates=[])
        nd.x_eddy = EddyMeta(iteration=it, beats=[])
        return nd
    monkeypatch.setattr(cp, "revise_decisions", fake_revise)

    calls = {"n": 0, "spans_at_success": None}

    def fake_compile(decisions, *a, **k):
        calls["n"] += 1
        spans = [round(p.end_s - p.start_s) for p in decisions.protected_moments]
        if calls["n"] == 1:
            raise CompileError([{"type": "cut_in_protected"}])  # force the repair path
        calls["spans_at_success"] = spans
        return Edl(sources={"camera": "x.mp4"}, ranges=[EdlRange(start=0, end=50)], total_duration_s=50.0)
    monkeypatch.setattr(cp, "compile_edl", fake_compile)

    out_decisions, edl = cp.compile_with_repair(tmp_path, d, provider=None, receipts=_NullReceipts(), cfg=cfg())
    # at the SUCCESSFUL compile (attempt 2, post-repair), the 600s protection must have been re-trimmed
    assert 600 not in calls["spans_at_success"], calls["spans_at_success"]
    assert all((p.end_s - p.start_s) <= 200 for p in out_decisions.protected_moments)


# ---- trim-to-fit ADOPT / REVERT gate (monkeypatched, no ffmpeg) ---------------------

def _patched_trim(monkeypatch, tmp_path, *, gates=True, judge_w=8.0, panel=True, judge_majors=0,
                  render_raises=False, base_w=8.0, base_majors=0, ceiling_min=5.0):
    """Wire trim_to_fit's QA/render/phrases dependencies to controlled stubs and return
    (edl, run, info-getter). edl starts at 420s over a ceiling_min ceiling."""
    edl, d, phrases = _trim_world()  # 420s: HOOK20 + WALK300 + ASIDE40 + PAYOFF60
    run = tmp_path
    (run / "iterations").mkdir(exist_ok=True)
    chosen = run / "iterations" / "01"
    chosen.mkdir(exist_ok=True)
    (chosen / "judge.json").write_text(json.dumps({
        "weighted": base_w,
        "defects": [{"severity": "major"}] * base_majors,
        "judge_unstable": False,
    }))

    import eddy.edit.simulate as sim_mod
    import eddy.qa.deterministic as det_mod
    import eddy.qa.judge as judge_mod
    import eddy.render.segments as seg_mod
    import eddy.transcribe.pack as pack_mod

    monkeypatch.setattr(pack_mod, "phrases", lambda rd: phrases)
    monkeypatch.setattr(sim_mod, "simulate", lambda *a, **k: {"target_s": 720, "boundary_cards": [], "duration_s": 0})

    def fake_render(*a, **k):
        if render_raises:
            raise RuntimeError("render boom")
        return None
    monkeypatch.setattr(seg_mod, "render_edl", fake_render)
    monkeypatch.setattr(det_mod, "run_deterministic", lambda *a, **k: {"pass": gates})
    monkeypatch.setattr(judge_mod, "run_judge", lambda *a, **k: {
        "weighted": judge_w, "defects": [{"severity": "major"}] * judge_majors, "judge_unstable": False})
    monkeypatch.setattr(judge_mod, "run_ship_panel", lambda *a, **k: {"ships": panel})

    c = cfg(enable_aggressive_trim=True, length_ceiling_minutes=ceiling_min, trim_judge_tolerance=0.5)
    info = trim_to_fit(edl, d, {"target_s": 720}, run, chosen, None, _NullReceipts(), c)
    return edl, info


def test_trim_adopts_when_all_checks_pass(tmp_path, monkeypatch):
    edl, info = _patched_trim(monkeypatch, tmp_path, ceiling_min=5.0)  # 300s ceiling, over 120s
    assert info["adopted"] is True and info["applied"] is True
    assert edl.total_duration_s < 420  # edl mutated in place
    # greedy minimal-set: WALK(300s) alone closes the 120s gap -> exactly one beat dropped
    assert len(info["beats_dropped"]) == 1 and info["beats_dropped"][0]["label"] == "WALKTHROUGH"
    assert info["ceiling_missed_s"] == 0.0


def test_trim_reverts_when_judge_drops(tmp_path, monkeypatch):
    edl, info = _patched_trim(monkeypatch, tmp_path, judge_w=7.0, base_w=8.0)  # 7.0 < 8.0 - 0.5
    assert info["adopted"] is False and "judge_held" in info["revert_reason"]
    assert edl.total_duration_s == 420  # untouched


def test_trim_reverts_when_panel_dissents(tmp_path, monkeypatch):
    edl, info = _patched_trim(monkeypatch, tmp_path, panel=False)
    assert info["adopted"] is False and "panel_ships" in info["revert_reason"]
    assert edl.total_duration_s == 420


def test_trim_reverts_on_new_majors(tmp_path, monkeypatch):
    edl, info = _patched_trim(monkeypatch, tmp_path, judge_majors=2, base_majors=0)
    assert info["adopted"] is False and "no_new_majors" in info["revert_reason"]
    assert edl.total_duration_s == 420


def test_trim_reverts_on_failed_gates(tmp_path, monkeypatch):
    edl, info = _patched_trim(monkeypatch, tmp_path, gates=False)
    assert info["adopted"] is False and "gates_pass" in info["revert_reason"]
    assert edl.total_duration_s == 420


def test_trim_reverts_on_validation_error(tmp_path, monkeypatch):
    edl, info = _patched_trim(monkeypatch, tmp_path, render_raises=True)
    assert info["adopted"] is False and info["revert_reason"].startswith("validation error:")
    assert edl.total_duration_s == 420


def test_trim_residual_logged_when_ceiling_unreachable(tmp_path, monkeypatch):
    # ceiling 1min: dropping WALK(300)+ASIDE(40)=340s leaves HOOK+PAYOFF=80s, still 20s over -> adopt + residual
    edl, info = _patched_trim(monkeypatch, tmp_path, ceiling_min=1.0)
    assert info["adopted"] is True
    assert info["ceiling_missed_s"] == 20.0 and info["duration_after_s"] == 80.0


def test_removable_excludes_cold_open_range(tmp_path):
    # a COLD_OPEN-tagged range inside an otherwise-removable beat span must never be selected
    beats = [{"label": "WALKTHROUGH", "start_s": 0, "end_s": 200}]
    ranges = [EdlRange(start=0, end=15, beat="COLD_OPEN"), EdlRange(start=20, end=200, beat="WALKTHROUGH")]
    edl = mk_edl(ranges)
    d = EditDecisions(retakes=[], cuts=[], protected_moments=[], shorts_candidates=[])
    d.x_eddy = EddyMeta(iteration=1, beats=beats)
    phrases = [{"start": i, "end": i + 1, "text": "narrating screen"} for i in range(20, 200, 3)]
    rem = _removable_beats(edl, d, phrases)
    all_idxs = [i for b in rem for i in b["range_idxs"]]
    assert 0 not in all_idxs  # the COLD_OPEN range index is never removable


# ---- protection budget --------------------------------------------------------------

def test_protection_budget_keeps_specific_drops_broad():
    pms = [
        ProtectedMoment(start_s=0, end_s=10),     # 10s
        ProtectedMoment(start_s=20, end_s=35),    # 15s
        ProtectedMoment(start_s=50, end_s=80),    # 30s
        ProtectedMoment(start_s=100, end_s=700),  # 600s over-protect
    ]
    kept, dropped = enforce_protection_budget(pms, source_s=1000.0, budget_frac=0.20)  # budget 200s
    assert sum(p.end_s - p.start_s for p in kept) <= 200.0
    assert [round(p.end_s - p.start_s) for p in dropped] == [600]
    assert all(p.end_s - p.start_s <= 30 for p in kept)


def test_protection_budget_under_budget_untouched():
    pms = [ProtectedMoment(start_s=0, end_s=10), ProtectedMoment(start_s=20, end_s=35)]
    kept, dropped = enforce_protection_budget(pms, source_s=1000.0, budget_frac=0.20)
    assert len(kept) == 2 and not dropped


# ---- raw beat density ---------------------------------------------------------------

def test_raw_beat_density_heaviest_first_and_wpm():
    beats = [
        {"label": "HOOK", "start_s": 0, "end_s": 30},
        {"label": "WALKTHROUGH", "start_s": 30, "end_s": 330},  # 300s span
    ]
    phrases = (
        [{"start": i, "end": i + 1, "text": "one two three"} for i in range(0, 30, 2)]
        + [{"start": i, "end": i + 1, "text": "slow"} for i in range(30, 330, 10)]
    )
    d = raw_beat_density(beats, phrases)
    assert d[0]["label"] == "WALKTHROUGH" and d[0]["span_s"] == 300.0
    # HOOK: 15 phrases x 3 words = 45 words over 30s = 90 wpm
    hook = next(b for b in d if b["label"] == "HOOK")
    assert hook["raw_wpm"] == 90.0


# ---- directive escalation -----------------------------------------------------------

def _over_sim():
    return {
        "under_ceiling": False, "duration_s": 2200, "ceiling_s": 840, "target_s": 720, "dead_air": [],
        "beat_density": [{"label": f"B{i}", "kept_s": 120 - i, "wpm": 150} for i in range(8)],
    }


def test_directive_escalates_with_streak():
    sim = _over_sim()
    reasons = [
        next(x for x in _directive_from({}, {"defects": []}, sim, s) if x["op"] == "drop_beat")["reason"]
        for s in (1, 2, 3)
    ]
    # heavy beats named: 4 -> 6 -> 8 (each hint carries one ' @ ')
    assert [r.count(" @ ") for r in reasons] == [4, 6, 8]
    assert len(reasons[2]) > len(reasons[1]) > len(reasons[0])
    assert "STILL" not in reasons[0] and "STILL" in reasons[1] and "ENTIRELY" in reasons[2]


def test_under_ceiling_has_no_over_directive():
    sim = {**_over_sim(), "under_ceiling": True}
    d = _directive_from({}, {"defects": []}, sim, 0)
    assert not any("OVER the" in x.get("reason", "") for x in d)


# ---- trim-to-fit selection ----------------------------------------------------------

def _trim_world():
    beats = [
        {"label": "HOOK", "start_s": 0, "end_s": 20},
        {"label": "WALKTHROUGH", "start_s": 20, "end_s": 320},   # long fast read-through -> removable
        {"label": "ASIDE", "start_s": 320, "end_s": 360},        # short -> removable but low score
        {"label": "PAYOFF", "start_s": 360, "end_s": 420},       # protected label -> never
    ]
    ranges = [
        EdlRange(start=0, end=20, beat="HOOK"),
        EdlRange(start=20, end=320, beat="WALKTHROUGH"),
        EdlRange(start=320, end=360, beat="ASIDE"),
        EdlRange(start=360, end=420, beat="PAYOFF"),
    ]
    edl = mk_edl(ranges)
    d = EditDecisions(retakes=[], cuts=[], protected_moments=[], shorts_candidates=[])
    d.x_eddy = EddyMeta(iteration=1, beats=beats)
    phrases = (
        [{"start": i, "end": i + 1, "text": "hook line here"} for i in range(0, 20, 4)]
        + [{"start": i, "end": i + 1, "text": "reading the screen out loud"} for i in range(20, 320, 3)]
        + [{"start": i, "end": i + 1, "text": "aside"} for i in range(320, 360, 8)]
        + [{"start": i, "end": i + 1, "text": "the payoff lands here"} for i in range(360, 420, 5)]
    )
    return edl, d, phrases


def test_removable_excludes_protected_labels_and_ranks_readthrough_first():
    edl, d, phrases = _trim_world()
    rem = _removable_beats(edl, d, phrases)
    labels = [b["label"] for b in rem]
    assert "HOOK" not in labels and "PAYOFF" not in labels
    assert labels[0] == "WALKTHROUGH"  # long + fast = lowest editorial value, removed first


def test_removable_excludes_protected_moment_overlap():
    edl, d, phrases = _trim_world()
    d.protected_moments = [ProtectedMoment(start_s=100, end_s=110, reason="demo")]
    rem = _removable_beats(edl, d, phrases)
    assert "WALKTHROUGH" not in [b["label"] for b in rem]


def test_trim_disabled_is_a_noop(tmp_path):
    edl, d, _ = _trim_world()
    before = edl.total_duration_s
    info = trim_to_fit(edl, d, {"target_s": 720}, tmp_path, tmp_path, None, _NullReceipts(), cfg())
    assert info["applied"] is False and edl.total_duration_s == before


def test_trim_under_ceiling_is_a_noop(tmp_path):
    edl, d, _ = _trim_world()
    before = edl.total_duration_s  # 420s; ceiling 10min = 600s -> under
    info = trim_to_fit(edl, d, {"target_s": 720}, tmp_path, tmp_path, None, _NullReceipts(),
                       cfg(enable_aggressive_trim=True, length_ceiling_minutes=10.0))
    assert info["applied"] is False and edl.total_duration_s == before


def test_recompute_total_is_speed_aware():
    ranges = [EdlRange(start=0, end=100, speed=1.0), EdlRange(start=100, end=200, speed=2.0)]
    assert _recompute_total(ranges) == 150.0  # 100 + 100/2


class _NullReceipts:
    def log(self, *a, **k):
        pass


# ---- real render regression: a range-dropped (trimmed) EDL still renders to its duration ----

def test_render_trimmed_edl_passes_av_drift(tmp_path):
    """Dropping a middle range creates a new splice; the concatenated render must still land on the
    recomputed EDL duration within av_drift tolerance. The in-memory tests never render."""
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
    # full 3-range edl, then the trimmed 2-range edl (middle beat removed -> a splice)
    full = [EdlRange(start=2, end=12), EdlRange(start=15, end=25), EdlRange(start=28, end=38)]
    trimmed = Edl(sources={"camera": str(src)}, ranges=[full[0], full[2]])
    trimmed.total_duration_s = _recompute_total(trimmed.ranges)  # 20.0
    out = tmp_path / "out.mp4"
    c = load_config()
    render_edl(trimmed, out, tmp_path, c.render, proxy=True)
    gate = av_drift(out, trimmed, c.gates.max_av_drift_s)
    assert gate["pass"], gate
