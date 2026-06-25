"""The agentic loop: iterate decisions -> compile -> simulate -> proxy -> judge -> gate
until done (or best attempt after max iterations), then final render + shorts + kit."""

from __future__ import annotations

from eddy.loop._diagnostics import (
    _budget_exhausted,
    _cost_cap_hit,
    _editorial_model_id,
    _fmt_dur,
    _loop_progress,
    _made_progress,
    _plateau_step,
    _record_model_pin,
)
from eddy.loop._directives import _directive_from
from eddy.loop._orchestration import _run_plan, autonomous_run, mine_shorts
from eddy.loop._phases import EditLoopError

__all__ = [
    # public surface
    "autonomous_run",
    "mine_shorts",
    "EditLoopError",
    # test-exposed privates
    "_directive_from",
    "_budget_exhausted",
    "_cost_cap_hit",
    "_made_progress",
    "_plateau_step",
    "_editorial_model_id",
    "_record_model_pin",
    "_fmt_dur",
    "_loop_progress",
    "_run_plan",
]
