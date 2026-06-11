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

    def record_attempt(self, iteration: int, gates_passed: bool, judge_score: float, duration_delta_s: float) -> None:
        self.data["attempts"] = [a for a in self.data["attempts"] if a["iteration"] != iteration]
        self.data["attempts"].append(
            {
                "iteration": iteration,
                "gates_passed": gates_passed,
                "judge_score": judge_score,
                "duration_delta_s": round(abs(duration_delta_s), 1),
            }
        )
        self.data["iteration"] = iteration
        self.data["best_iter"] = self.best()["iteration"]
        self.save()

    def best(self) -> dict:
        if not self.data["attempts"]:
            raise RuntimeError("no attempts recorded")
        return max(
            self.data["attempts"],
            key=lambda a: (a["gates_passed"], a["judge_score"], -a["duration_delta_s"]),
        )

    def set_phase(self, phase: str) -> None:
        self.data["phase"] = phase
        self.save()


def print_status(run_dir: Path) -> None:
    s = RunState(run_dir)
    print(json.dumps(s.data, indent=1))
