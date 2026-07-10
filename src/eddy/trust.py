"""Owner dogfood trust gate for no-review language."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contract import canonical_contract


def trust_status(ledger: Path) -> dict[str, Any]:
    if not ledger.exists():
        return {
            "green_owner_runs": 0,
            "required": canonical_contract().no_review_dogfoods_required,
            "no_review_unlocked": False,
        }
    payload = json.loads(ledger.read_text())
    if payload.get("schema_version") != "eddy-trust-v1":
        raise ValueError("trust_ledger_schema_invalid")
    accepted: set[str] = set()
    for run in payload.get("runs", []):
        if (
            run.get("green") is True
            and run.get("owner_approved") is True
            and run.get("critical_failures") == 0
            and isinstance(run.get("id"), str)
        ):
            accepted.add(run["id"])
    required = canonical_contract().no_review_dogfoods_required
    return {
        "green_owner_runs": len(accepted),
        "required": required,
        "no_review_unlocked": len(accepted) >= required,
    }

