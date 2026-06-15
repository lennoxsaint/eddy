"""v0.4: cumulative loop budget — wall-clock + model-call ceiling so a pathological source on a
cloud brain can't run unbounded time/cost. (max_model_calls_per_iteration was dead config.)"""

from types import SimpleNamespace

from eddy.loop.controller import _budget_exhausted


def _loop(wall_min=120.0, max_calls=60):
    return SimpleNamespace(max_wall_clock_minutes=wall_min, max_total_model_calls=max_calls)


def test_under_both_budgets_continues():
    assert _budget_exhausted(elapsed_s=30.0, model_calls=5, loop=_loop()) is False


def test_over_wall_clock_stops():
    assert _budget_exhausted(elapsed_s=120 * 60 + 1, model_calls=5, loop=_loop(wall_min=120.0)) is True


def test_at_or_over_model_call_cap_stops():
    assert _budget_exhausted(elapsed_s=30.0, model_calls=60, loop=_loop(max_calls=60)) is True


def test_just_under_call_cap_continues():
    assert _budget_exhausted(elapsed_s=30.0, model_calls=59, loop=_loop(max_calls=60)) is False
