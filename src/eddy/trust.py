"""Owner dogfood trust gate for no-review language."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from .contract import canonical_contract
from .runtime import REQUIRED_FINAL_GATES


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_fingerprint(source_lock: dict[str, Any]) -> str:
    encoded = json.dumps(source_lock.get("before", {}), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _is_proven_owner_run(run: object, runs_root: Path | None) -> bool:
    if not isinstance(run, dict):
        return False
    source_hash = run.get("source_hash")
    qa_hash = run.get("qa_receipt_sha256")
    declared = (
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
    if not declared or runs_root is None:
        return False
    run_dir = runs_root / str(run["id"])
    final = run_dir / "final"
    try:
        state = json.loads((run_dir / "state.json").read_text())
        verification = json.loads((run_dir / "verification.json").read_text())
        source_lock = json.loads((run_dir / "source-lock.json").read_text())
        provider_rows = [
            json.loads(line)
            for line in (run_dir / "final" / "provider-receipts.jsonl").read_text().splitlines()
            if line.strip()
        ]
        artifact_manifest = json.loads((final / "artifact-manifest.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    longs = sorted(final.glob("long-*.mp4"))
    shorts = sorted((final / "shorts").glob("*.mp4"))
    providers = {
        row.get("provider") for row in provider_rows if row.get("event") == "descript_provider"
    }
    effects = [
        row for row in provider_rows
        if row.get("event") == "descript_effect_survival" and row.get("status") == "pass"
    ]
    video_artifacts = {
        path.relative_to(final).as_posix() for path in (*longs, *shorts)
    }
    provider_artifacts = {
        str(row.get("artifact"))
        for row in provider_rows
        if row.get("event") == "descript_provider"
        and row.get("access_level") == "private"
        and row.get("provider") in {"descript_api", "descript_host_connector"}
    }
    effect_artifacts = {
        str(row.get("artifact"))
        for row in effects
    }
    manifested = artifact_manifest.get("files", {})
    current_files = {
        path.relative_to(final).as_posix(): _sha256(path)
        for path in final.rglob("*")
        if path.is_file() and path.name != "artifact-manifest.json"
    }
    return (
        state.get("state") == "completed"
        and state.get("id") == run["id"]
        and len(longs) == 3
        and all(path.stat().st_size > 0 for path in longs)
        and 3 <= len(shorts) <= 5
        and all(path.stat().st_size > 0 for path in shorts)
        and verification.get("blockers") == []
        and REQUIRED_FINAL_GATES <= set(verification.get("gates", {}))
        and all(verification["gates"].values())
        and source_lock.get("before") == source_lock.get("after")
        and _source_fingerprint(source_lock) == source_hash
        and _sha256(final / "qa.json") == qa_hash
        and providers <= {"descript_api", "descript_host_connector"}
        and bool(providers)
        and provider_artifacts == video_artifacts
        and effect_artifacts == video_artifacts
        and manifested == current_files
    )


def trust_status(ledger: Path, *, runs_root: Path | None = None) -> dict[str, Any]:
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
        if _is_proven_owner_run(run, runs_root) and run["id"] not in accepted:
            accepted.add(run["id"])
            accepted_sources.add(run["source_hash"])
    required = canonical_contract().no_review_dogfoods_required
    proven_count = min(len(accepted), len(accepted_sources))
    return {
        "green_owner_runs": proven_count,
        "required": required,
        "no_review_unlocked": proven_count >= required,
    }
