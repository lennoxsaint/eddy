"""Host-kernel repair-loop stop rules.

The host can provide creative intent repeatedly, but Eddy owns the loop budget and stop conditions:
pass when gates pass, continue while objective evidence improves, and block when the same failure
repeats without progress.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_REPAIR_PASSES = 10
MAX_REPAIR_SECONDS = 3 * 60 * 60
NO_PROGRESS_LIMIT = 2


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def qa_failure_signature(qa: dict[str, Any] | None) -> str:
    if not qa:
        return ""
    failures: list[str] = []
    for key, value in sorted(qa.items()):
        if key == "pass":
            continue
        if isinstance(value, dict) and value.get("pass") is False:
            failures.append(key)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("pass") is False:
                    failures.append(f"{key}:{item.get('name') or item.get('gate') or len(failures)}")
    return json.dumps(failures, sort_keys=True)


def quality_value(entry: dict[str, Any]) -> float:
    for key in ("quality", "quality_score", "judge_score", "score"):
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    qa = entry.get("qa")
    if isinstance(qa, dict):
        total = failed = 0
        for value in qa.values():
            if isinstance(value, dict) and "pass" in value:
                total += 1
                failed += 0 if value.get("pass") else 1
        if total:
            return float(total - failed) / float(total)
    return 0.0


def evaluate_repair_loop(
    history: list[dict[str, Any]],
    *,
    elapsed_s: float,
    max_passes: int = MAX_REPAIR_PASSES,
    max_elapsed_s: int = MAX_REPAIR_SECONDS,
    no_progress_limit: int = NO_PROGRESS_LIMIT,
) -> dict[str, Any]:
    if any(entry.get("qa_pass") is True or entry.get("status") == "passed" for entry in history):
        return {"status": "passed", "stop_reason": "gates_passed", "repair_passes": len(history)}
    if len(history) >= max_passes:
        return {"status": "blocked", "stop_reason": "repair_pass_budget_exhausted", "repair_passes": len(history)}
    if elapsed_s >= max_elapsed_s:
        return {
            "status": "blocked",
            "stop_reason": "repair_time_budget_exhausted",
            "repair_passes": len(history),
            "elapsed_s": round(elapsed_s, 1),
        }
    if len(history) >= no_progress_limit + 1:
        tail = history[-(no_progress_limit + 1):]
        signatures = [entry.get("failure_signature") or qa_failure_signature(entry.get("qa")) for entry in tail]
        qualities = [quality_value(entry) for entry in tail]
        same_failure = bool(signatures[0]) and len(set(signatures)) == 1
        no_quality_gain = max(qualities) <= qualities[0] + 0.001
        if same_failure and no_quality_gain:
            return {
                "status": "blocked",
                "stop_reason": "same_qa_failure_without_improvement",
                "repair_passes": len(history),
                "failure_signature": signatures[-1],
            }
    return {"status": "continue", "stop_reason": "", "repair_passes": len(history)}


def history_path(run_dir: Path) -> Path:
    return Path(run_dir) / "host-agent" / "repair-history.json"


def started_path(run_dir: Path) -> Path:
    return Path(run_dir) / "host-agent" / "loop-started.json"


def ensure_started(run_dir: Path) -> str:
    path = started_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            started_at = data.get("started_at")
            if isinstance(started_at, str) and started_at:
                return started_at
        except (OSError, json.JSONDecodeError):
            pass
    started_at = utc_now_iso()
    path.write_text(json.dumps({"started_at": started_at}, indent=1))
    return started_at


def elapsed_since_started(run_dir: Path) -> float:
    started_at = ensure_started(run_dir)
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return 0.0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())


def read_history(run_dir: Path) -> list[dict[str, Any]]:
    path = history_path(run_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def append_history(run_dir: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    path = history_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    history = read_history(run_dir)
    history.append({"created_at": utc_now_iso(), **entry})
    path.write_text(json.dumps(history, indent=1))
    return history
