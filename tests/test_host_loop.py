from __future__ import annotations

from eddy.host_loop import evaluate_repair_loop, qa_failure_signature


def test_green_gates_stop_host_loop():
    out = evaluate_repair_loop([{"status": "passed", "qa_pass": True}], elapsed_s=12)
    assert out["status"] == "passed"
    assert out["stop_reason"] == "gates_passed"


def test_repeated_same_qa_failure_without_improvement_blocks():
    history = [
        {"failure_signature": '["dead_air"]', "quality": 0.5},
        {"failure_signature": '["dead_air"]', "quality": 0.5},
        {"failure_signature": '["dead_air"]', "quality": 0.5},
    ]
    out = evaluate_repair_loop(history, elapsed_s=120)
    assert out["status"] == "blocked"
    assert out["stop_reason"] == "same_qa_failure_without_improvement"


def test_improvement_resets_no_progress_blocker():
    history = [
        {"failure_signature": '["dead_air"]', "quality": 0.5},
        {"failure_signature": '["dead_air"]', "quality": 0.6},
        {"failure_signature": '["dead_air"]', "quality": 0.7},
    ]
    out = evaluate_repair_loop(history, elapsed_s=120)
    assert out["status"] == "continue"


def test_repair_loop_respects_pass_and_time_budget():
    pass_budget = evaluate_repair_loop([{"failure_signature": "x"} for _ in range(10)], elapsed_s=10)
    time_budget = evaluate_repair_loop([], elapsed_s=10800)

    assert pass_budget["status"] == "blocked"
    assert pass_budget["stop_reason"] == "repair_pass_budget_exhausted"
    assert time_budget["status"] == "blocked"
    assert time_budget["stop_reason"] == "repair_time_budget_exhausted"


def test_qa_failure_signature_is_stable():
    qa = {
        "pass": False,
        "dead_air": {"pass": False},
        "loudness": {"pass": True},
        "boundaries": [{"name": "cut_1", "pass": False}],
    }
    assert qa_failure_signature(qa) == '["boundaries:cut_1", "dead_air"]'
