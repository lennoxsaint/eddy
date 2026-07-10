import json
from pathlib import Path

from eddy.trust import trust_status


def test_no_review_claim_remains_locked_until_five_green_owner_runs(tmp_path: Path) -> None:
    ledger = tmp_path / "trust-ledger.json"
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": []}))

    assert trust_status(ledger)["no_review_unlocked"] is False

    runs = [
        {"id": f"dogfood-{index}", "owner_approved": True, "critical_failures": 0, "green": True}
        for index in range(5)
    ]
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": runs}))

    status = trust_status(ledger)
    assert status["green_owner_runs"] == 5
    assert status["no_review_unlocked"] is True


def test_duplicate_or_red_runs_do_not_unlock_claim(tmp_path: Path) -> None:
    ledger = tmp_path / "trust-ledger.json"
    runs = [
        {"id": "same", "owner_approved": True, "critical_failures": 0, "green": True},
        {"id": "same", "owner_approved": True, "critical_failures": 0, "green": True},
        {"id": "red", "owner_approved": True, "critical_failures": 1, "green": False},
    ]
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": runs}))

    assert trust_status(ledger)["green_owner_runs"] == 1
