import json
from pathlib import Path

from eddy.trust import trust_status


def proven_run(index: int, *, run_id: str | None = None, source_hash: str | None = None) -> dict:
    return {
        "id": run_id or f"dogfood-{index}",
        "owner_approved": True,
        "critical_failures": 0,
        "green": True,
        "proof_state": "final_qa_passed",
        "real_footage": True,
        "fake_modes": False,
        "descript_provider": "descript_api",
        "hyperframes_provider": "hyperframes",
        "source_hash": source_hash or f"{index + 1:064x}",
        "qa_receipt_sha256": f"{index + 101:064x}",
    }


def test_no_review_claim_remains_locked_until_five_green_owner_runs(tmp_path: Path) -> None:
    ledger = tmp_path / "trust-ledger.json"
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": []}))

    assert trust_status(ledger)["no_review_unlocked"] is False

    runs = [proven_run(index) for index in range(5)]
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": runs}))

    status = trust_status(ledger)
    assert status["green_owner_runs"] == 5
    assert status["no_review_unlocked"] is True


def test_duplicate_or_red_runs_do_not_unlock_claim(tmp_path: Path) -> None:
    ledger = tmp_path / "trust-ledger.json"
    runs = [
        proven_run(0, run_id="same"),
        proven_run(1, run_id="same"),
        {"id": "red", "owner_approved": True, "critical_failures": 1, "green": False},
    ]
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": runs}))

    assert trust_status(ledger)["green_owner_runs"] == 1


def test_self_asserted_rows_without_proof_evidence_do_not_unlock(tmp_path: Path) -> None:
    ledger = tmp_path / "trust-ledger.json"
    rows = [
        {"id": f"fake-{index}", "owner_approved": True, "critical_failures": 0, "green": True}
        for index in range(5)
    ]
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": rows}))

    assert trust_status(ledger)["green_owner_runs"] == 0
    assert trust_status(ledger)["no_review_unlocked"] is False
