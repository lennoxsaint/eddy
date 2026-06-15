"""Loop state ranking, judge consistency checks, directive building — stubbed providers."""



from eddy.loop.state import RunState
from eddy.qa.judge import _consistent, weighted_score


def test_weighted_score():
    scores = {"hook_integrity": 10, "boundary_continuity": 10, "pacing": 10, "completeness": 10, "ending_cta": 10}
    assert weighted_score(scores) == 10.0
    scores["boundary_continuity"] = 0  # out of the 1-10 rubric range -> clamped to the 1 floor (v0.4)
    assert weighted_score(scores) == round(83 / 11, 2)  # 7.55 (0 clamps to 1, weight 3 of 11)


def test_consistency_rejects_inflated_score():
    result = {
        "scores": {k: 9 for k in ("hook_integrity", "boundary_continuity", "pacing", "completeness", "ending_cta")},
        "defects": [
            {"severity": "major"}, {"severity": "major"},
        ],
    }
    assert not _consistent(result)


def test_consistency_rejects_low_score_no_defects():
    result = {
        "scores": {k: 3 for k in ("hook_integrity", "boundary_continuity", "pacing", "completeness", "ending_cta")},
        "defects": [],
    }
    assert not _consistent(result)


def test_consistency_accepts_aligned_verdict():
    result = {
        "scores": {k: 8 for k in ("hook_integrity", "boundary_continuity", "pacing", "completeness", "ending_cta")},
        "defects": [{"severity": "minor"}],
    }
    assert _consistent(result)


def test_state_best_attempt_ranking(tmp_path):
    s = RunState(tmp_path)
    s.record_attempt(1, gates_passed=False, judge_score=9.0, duration_delta_s=5)
    s.record_attempt(2, gates_passed=True, judge_score=6.0, duration_delta_s=50)
    s.record_attempt(3, gates_passed=True, judge_score=6.0, duration_delta_s=10)
    best = s.best()
    # gates beat judge score; closer duration breaks the tie
    assert best["iteration"] == 3


def test_state_resume_roundtrip(tmp_path):
    s = RunState(tmp_path)
    s.record_attempt(1, True, 8.5, 3)
    s2 = RunState(tmp_path)
    assert s2.data["iteration"] == 1
    assert s2.data["best_iter"] == 1


def test_state_rerecord_same_iteration_replaces(tmp_path):
    s = RunState(tmp_path)
    s.record_attempt(1, False, 2.0, 100)
    s.record_attempt(1, True, 9.0, 1)
    assert len(s.data["attempts"]) == 1
    assert s.best()["judge_score"] == 9.0


def test_directive_builder_caps_and_types():
    from eddy.loop.controller import _directive_from

    sim = {
        "dead_air": [{"after_out_s": 10.0, "gap_s": 2.0, "before": "x"}] * 7,
        "verdicts": {"duration_in_band": False},
        "duration_s": 900.0,
        "target_s": 720.0,
    }
    judge = {
        "defects": [
            {"severity": "major", "fix_op": "restore", "out_s": 1.0, "quote": "q", "type": "orphan_reference", "fix_note": "n"}
        ]
        * 5
    }
    directive = _directive_from({}, judge, sim)
    assert len(directive) <= 10
    ops = {d["op"] for d in directive}
    assert "tighten_gap" in ops  # dead air + over duration
    assert "restore" in ops  # judge defects


def test_no_edl_precondition_and_error_type(tmp_path):
    """Contract for the loop's all-iterations-failed guard: a state with only failed
    (compile-error) attempts selects a best iteration whose dir has NO edl.json — the exact
    precondition the guard checks — and EditLoopError is a RuntimeError so the CLI catches it."""
    from eddy.loop.controller import EditLoopError

    assert issubclass(EditLoopError, RuntimeError)

    run_dir = tmp_path / "run"
    (run_dir / "iterations" / "03").mkdir(parents=True)  # best dir exists, never got an edl.json
    state = RunState(run_dir)
    state.record_attempt(3, False, 0.0, 99.0)  # compile-failed attempt (gates_passed=False)

    chosen_dir = run_dir / "iterations" / f"{state.best()['iteration']:02d}"
    assert chosen_dir.name == "03"
    assert not (chosen_dir / "edl.json").exists()  # -> guard raises EditLoopError, no FileNotFoundError
