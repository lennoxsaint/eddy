"""v0.3 hybrid quality metric: monotonic in defects, not gameable by length."""

from eddy.config import load_config
from eddy.edit.schema import EditDecisions
from eddy.qa.quality import OBJ_WEIGHTS, _orphan_count, quality_score

CFG = load_config()
STABLE = {"weighted": 8.0, "judge_unstable": False}
PHRASE = [{"start": 0, "end": 1, "out_start": 0, "out_end": 1, "text": "hi there"}]


def mk_decisions(cold_open=None, beats=None):
    d = EditDecisions()
    if cold_open:
        d.cold_open = cold_open
    if beats:
        d.x_eddy.beats = beats
    return d


def mk_sim(dead_air=0, beat_density=None, duration_s=600.0):
    return {
        "dead_air": [{"gap_s": 2} for _ in range(dead_air)],
        "beat_density": beat_density or [],
        "duration_s": duration_s,
    }


def q(sim, judge=STABLE, kept=None, decisions=None):
    return quality_score(sim, judge, kept or PHRASE, decisions or mk_decisions(cold_open={"start_s": 1, "end_s": 5}), [], CFG)


def test_objective_weights_sum_to_one():
    assert abs(sum(OBJ_WEIGHTS.values()) - 1.0) < 1e-9


def test_dead_air_is_monotonic():
    assert q(mk_sim(dead_air=2))["objective"] < q(mk_sim(dead_air=0))["objective"]


def test_pacing_drag_lowers_score():
    clean = mk_sim(beat_density=[{"label": "a", "wpm": 150, "kept_s": 60}])
    draggy = mk_sim(beat_density=[{"label": "a", "wpm": 240, "kept_s": 90}])
    assert q(draggy)["components"]["pacing"] < q(clean)["components"]["pacing"]


def test_over_ceiling_penalizes_being_short_does_not():
    ceiling = CFG.loop.length_ceiling_minutes * 60
    under = q(mk_sim(duration_s=ceiling - 120))
    over = q(mk_sim(duration_s=ceiling * 2))
    assert under["ceiling_penalty"] == 0.0
    assert over["ceiling_penalty"] > 0.0
    assert over["quality"] < under["quality"]


def test_shorter_without_removing_defect_is_not_rewarded():
    # same single dead-air defect, just shorter (both under ceiling) -> no length bonus
    longer = q(mk_sim(dead_air=1, duration_s=400))
    shorter = q(mk_sim(dead_air=1, duration_s=80))
    assert shorter["quality"] <= longer["quality"] + 1e-9


def test_hook_floor_vs_present():
    present = q(mk_sim())["components"]["hook_present"]  # cold_open set
    absent = quality_score(
        mk_sim(), STABLE,
        [{"start": 0, "end": 1, "out_start": 5, "out_end": 6, "text": "x"}],
        mk_decisions(), [], CFG,
    )["components"]["hook_present"]
    assert present == 10.0 and absent == 4.0


def test_unstable_judge_caps_critic_at_5():
    res = q(mk_sim(), judge={"weighted": 9.0, "judge_unstable": True})
    assert res["critic"] == 5.0


def test_orphaned_setup_detected():
    kept = [
        {"start": 0, "end": 2, "text": "now let's look at the scripts"},
        {"start": 50, "end": 52, "text": "and the winner is fable"},  # payoff cut: 48s jump
    ]
    assert _orphan_count(kept) == 1
    # adjacent payoff (no big jump) is not an orphan
    near = [
        {"start": 0, "end": 2, "text": "now let's look at the scripts"},
        {"start": 3, "end": 5, "text": "here is script one"},
    ]
    assert _orphan_count(near) == 0
