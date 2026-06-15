"""Run state: iteration tracking, attempt ranking, resume support."""

from __future__ import annotations

import json
from pathlib import Path


class RunState:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "state.json"
        self.data = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"iteration": 0, "attempts": [], "best_iter": None, "phase": "created"}
        )

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=1))

    def record_attempt(
        self,
        iteration: int,
        gates_passed: bool,
        judge_score: float,
        duration_delta_s: float,
        quality: float | None = None,
        components: dict | None = None,
        judge_unstable: bool = False,
        over_ceiling_s: float = 0.0,
    ) -> None:
        self.data["attempts"] = [a for a in self.data["attempts"] if a["iteration"] != iteration]
        self.data["attempts"].append(
            {
                "iteration": iteration,
                "gates_passed": gates_passed,
                "judge_score": judge_score,
                "duration_delta_s": round(abs(duration_delta_s), 1),
                "quality": quality,
                "components": components,
                "judge_unstable": judge_unstable,
                "over_ceiling_s": round(over_ceiling_s, 1),
            }
        )
        self.data["iteration"] = iteration
        self.data["best_iter"] = self.best()["iteration"]
        self.save()

    def best(self) -> dict:
        if not self.data["attempts"]:
            raise RuntimeError("no attempts recorded")

        def key(a: dict):
            gates = a["gates_passed"]
            # A gate-passing attempt always outranks a gate-failing one.
            # v0.3.3 (EDD-83): within a gate level, rank closeness-to-ceiling in ~2-minute BANDS
            # BEFORE quality, for BOTH gate levels. v0.3 only applied feasibility to gate-FAILING
            # attempts, so among gate-PASSING but over-ceiling cuts it maximized quality and shipped
            # the LONGEST one (the v0.3.2 dogfood shipped a 1694s-over cut over a 1452s-over cut that
            # the loop had worked to reach). Banding (not raw seconds) means a materially shorter cut
            # wins but small length differences still defer to quality — honoring "never sacrifice
            # quality to force the number". Compile-failed attempts (over_ceiling_s=1e9) stay
            # maximally infeasible. An under-ceiling attempt (band 0) outranks any over-ceiling one.
            feasible_band = -round(max(0.0, a.get("over_ceiling_s", 0.0)) / 120.0)
            q = a.get("quality")
            if q is None:  # pre-v0.3 state.json — fall back to judge score
                q = a.get("judge_score", 0.0)
            return (gates, feasible_band, q, -a["duration_delta_s"])

        return max(self.data["attempts"], key=key)

    def set_plateau(self, no_improve: int, prev_best_q: float, best_over: float | None = None) -> None:
        self.data["no_improve"] = no_improve
        self.data["prev_best_q"] = prev_best_q
        # v0.3.2: min over_ceiling_s seen so far — the length convergence axis the
        # feasibility-gated plateau reads (persisted so --resume keeps the streak honest).
        if best_over is not None:
            self.data["best_over"] = best_over
        self.save()

    def set_phase(self, phase: str) -> None:
        self.data["phase"] = phase
        self.save()


def print_status(run_dir: Path) -> None:
    s = RunState(run_dir)
    print(json.dumps(s.data, indent=1))
