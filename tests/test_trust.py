import json
import hashlib
from pathlib import Path

from eddy.runtime import REQUIRED_FINAL_GATES
from eddy.trust import trust_status


def proven_run(index: int, runs_root: Path, *, run_id: str | None = None) -> dict:
    job_id = run_id or f"dogfood-{index}"
    run_dir = runs_root / job_id
    final = run_dir / "final"
    shorts = final / "shorts"
    shorts.mkdir(parents=True, exist_ok=True)
    for name in ("long-primary.mp4", "long-alternate-a.mp4", "long-alternate-b.mp4"):
        (final / name).write_bytes(b"real-video")
    for short_index in range(3):
        (shorts / f"{short_index}.mp4").write_bytes(b"real-short")
    qa = final / "qa.json"
    qa.write_text('{"pass":true}\n')
    source_map = {f"/source/{index}.mp4": f"{index + 1:064x}"}
    (run_dir / "state.json").write_text(
        json.dumps({"id": job_id, "state": "completed"}) + "\n"
    )
    (run_dir / "verification.json").write_text(
        json.dumps({"gates": {gate: True for gate in REQUIRED_FINAL_GATES}, "blockers": []}) + "\n"
    )
    (run_dir / "source-lock.json").write_text(
        json.dumps({"before": source_map, "after": source_map}) + "\n"
    )
    receipts = []
    artifacts = [
        "long-primary.mp4",
        "long-alternate-a.mp4",
        "long-alternate-b.mp4",
        "shorts/0.mp4",
        "shorts/1.mp4",
        "shorts/2.mp4",
    ]
    for artifact in artifacts:
        receipts.extend(
            [
                {
                    "event": "descript_provider",
                    "provider": "descript_api",
                    "access_level": "private",
                    "artifact": artifact,
                },
                {"event": "descript_effect_survival", "status": "pass", "artifact": artifact},
            ]
        )
    (final / "provider-receipts.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in receipts)
    )
    manifest_files = {
        path.relative_to(final).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in final.rglob("*")
        if path.is_file() and path.name != "artifact-manifest.json"
    }
    (final / "artifact-manifest.json").write_text(
        json.dumps({"files": manifest_files}, sort_keys=True) + "\n"
    )
    source_hash = hashlib.sha256(
        json.dumps(source_map, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "id": job_id,
        "owner_approved": True,
        "critical_failures": 0,
        "green": True,
        "proof_state": "final_qa_passed",
        "real_footage": True,
        "fake_modes": False,
        "descript_provider": "descript_api",
        "hyperframes_provider": "hyperframes",
        "source_hash": source_hash,
        "qa_receipt_sha256": hashlib.sha256(qa.read_bytes()).hexdigest(),
    }


def test_no_review_claim_remains_locked_until_five_green_owner_runs(tmp_path: Path) -> None:
    ledger = tmp_path / "trust-ledger.json"
    runs_root = tmp_path / "runs"
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": []}))

    assert trust_status(ledger, runs_root=runs_root)["no_review_unlocked"] is False

    runs = [proven_run(index, runs_root) for index in range(5)]
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": runs}))

    status = trust_status(ledger, runs_root=runs_root)
    assert status["green_owner_runs"] == 5
    assert status["no_review_unlocked"] is True


def test_duplicate_or_red_runs_do_not_unlock_claim(tmp_path: Path) -> None:
    ledger = tmp_path / "trust-ledger.json"
    runs_root = tmp_path / "runs"
    runs = [
        proven_run(0, runs_root, run_id="same"),
        proven_run(1, runs_root, run_id="same"),
        {"id": "red", "owner_approved": True, "critical_failures": 1, "green": False},
    ]
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": runs}))

    assert trust_status(ledger, runs_root=runs_root)["green_owner_runs"] == 1


def test_self_asserted_rows_without_proof_evidence_do_not_unlock(tmp_path: Path) -> None:
    ledger = tmp_path / "trust-ledger.json"
    rows = [
        {"id": f"fake-{index}", "owner_approved": True, "critical_failures": 0, "green": True}
        for index in range(5)
    ]
    ledger.write_text(json.dumps({"schema_version": "eddy-trust-v1", "runs": rows}))

    assert trust_status(ledger)["green_owner_runs"] == 0
    assert trust_status(ledger)["no_review_unlocked"] is False
