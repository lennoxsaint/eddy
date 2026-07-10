"""Owner dogfood trust gate for no-review language."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contract import canonical_contract


def _is_proven_owner_run(run: object) -> bool:
    if not isinstance(run, dict):
        return False
    source_hash = run.get("source_hash")
    qa_hash = run.get("qa_receipt_sha256")
    return (
        run.get("green") is True
        and run.get("owner_approved") is True
        and run.get("critical_failures") == 0
        and run.get("proof_state") == "final_qa_passed"
        and run.get("real_footage") is True
        and run.get("fake_modes") is False
        and run.get("descript_provider") in {"descript_api", "descript_host_connector"}
        and run.get("hyperframes_provider") == "hyperframes"
        and isinstance(run.get("id"), str)
        and isinstance(source_hash, str)
        and len(source_hash) == 64
        and isinstance(qa_hash, str)
        and len(qa_hash) == 64
    )


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
    accepted_sources: set[str] = set()
    for run in payload.get("runs", []):
        if _is_proven_owner_run(run) and run["id"] not in accepted:
            accepted.add(run["id"])
            accepted_sources.add(run["source_hash"])
    required = canonical_contract().no_review_dogfoods_required
    proven_count = min(len(accepted), len(accepted_sources))
    return {
        "green_owner_runs": proven_count,
        "required": required,
        "no_review_unlocked": proven_count >= required,
    }
