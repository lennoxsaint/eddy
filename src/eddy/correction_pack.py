"""Versioned, project-local correction contracts for one Eddy run."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


CORRECTION_PACK_SCHEMA = "eddy-correction-pack-v1"
CORRECTION_LAYERS = {"eddy_core", "owner_profile", "project_correction_pack"}


class CorrectionPackError(ValueError):
    """A correction pack is ambiguous, unsafe, or incomplete."""


def materialize_correction_pack(
    run_dir: Path,
    *,
    project_id: str,
    explicit: str | Path | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and atomically snapshot one run-local correction pack."""

    payload, provenance = _load_or_default(project_id, explicit)
    normalized = validate_correction_pack(payload)
    run_dir.mkdir(parents=True, exist_ok=True)
    output = run_dir / "correction-pack.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    return {
        "schema_version": "eddy-correction-pack-ref-v1",
        "path": str(output),
        "ref": output.relative_to(run_dir).as_posix(),
        "sha256": _sha256(output),
        "project_id": normalized["project_id"],
        "provenance": provenance,
    }


def validate_correction_pack(value: object) -> dict[str, Any]:
    """Require traceable, single-owner corrections with explicit acceptance proof."""

    if not isinstance(value, dict) or value.get("schema_version") != CORRECTION_PACK_SCHEMA:
        raise CorrectionPackError("correction_pack_schema_invalid")
    project_id = _text(value.get("project_id"), "correction_pack_project_id_required")
    if value.get("public_safe") is not True:
        raise CorrectionPackError("correction_pack_public_safe_required")
    if value.get("unsafe_ledger_bodies_reopened") is not False:
        raise CorrectionPackError("correction_pack_unsafe_ledger_boundary_invalid")
    raw = value.get("corrections")
    if not isinstance(raw, list):
        raise CorrectionPackError("correction_pack_rows_invalid")
    corrections: list[dict[str, Any]] = []
    ids: set[str] = set()
    active_targets: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise CorrectionPackError("correction_pack_row_invalid")
        correction_id = _text(item.get("id"), "correction_pack_id_required")
        if correction_id in ids:
            raise CorrectionPackError(f"correction_pack_id_duplicated:{correction_id}")
        ids.add(correction_id)
        target = _text(item.get("target"), f"correction_pack_target_required:{correction_id}")
        layer = item.get("owning_layer")
        if layer not in CORRECTION_LAYERS:
            raise CorrectionPackError(f"correction_pack_layer_invalid:{correction_id}")
        source_ref = _safe_ref(
            item.get("source_ref"), f"correction_pack_source_ref_invalid:{correction_id}"
        )
        acceptance_probe = _text(
            item.get("acceptance_probe"),
            f"correction_pack_acceptance_probe_required:{correction_id}",
        )
        evidence_schema = _text(
            item.get("evidence_schema"),
            f"correction_pack_evidence_schema_required:{correction_id}",
        )
        supersedes = item.get("supersedes", [])
        if not isinstance(supersedes, list) or not all(
            isinstance(row, str) and row.strip() for row in supersedes
        ):
            raise CorrectionPackError(f"correction_pack_supersedes_invalid:{correction_id}")
        timecode = item.get("approximate_timecode")
        if timecode is not None and (not isinstance(timecode, str) or not timecode.strip()):
            raise CorrectionPackError(f"correction_pack_timecode_invalid:{correction_id}")
        status = item.get("status", "active")
        if status not in {"active", "superseded"}:
            raise CorrectionPackError(f"correction_pack_status_invalid:{correction_id}")
        if status == "active":
            previous = active_targets.get(target)
            if previous is not None and previous not in supersedes:
                raise CorrectionPackError(f"correction_pack_active_target_ambiguous:{target}")
            active_targets[target] = correction_id
        corrections.append(
            {
                "id": correction_id,
                "target": target,
                "owning_layer": layer,
                "source_ref": source_ref,
                "approximate_timecode": timecode.strip() if isinstance(timecode, str) else None,
                "acceptance_probe": acceptance_probe,
                "evidence_schema": evidence_schema,
                "supersedes": list(supersedes),
                "status": status,
            }
        )
    unknown_superseded = sorted(
        superseded
        for row in corrections
        for superseded in row["supersedes"]
        if superseded not in ids
    )
    if unknown_superseded:
        raise CorrectionPackError(
            f"correction_pack_supersedes_unknown:{','.join(unknown_superseded)}"
        )
    return {
        "schema_version": CORRECTION_PACK_SCHEMA,
        "project_id": project_id,
        "public_safe": True,
        "unsafe_ledger_bodies_reopened": False,
        "timecode_policy": "locator_only_source_and_frame_inspection_controls",
        "corrections": corrections,
    }


def _load_or_default(
    project_id: str,
    explicit: str | Path | dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(explicit, dict):
        return dict(explicit), {"kind": "inline", "source_ref": None}
    if isinstance(explicit, (str, Path)):
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise CorrectionPackError(f"correction_pack_missing:{path}")
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CorrectionPackError(f"correction_pack_invalid:{path}") from exc
        if not isinstance(payload, dict):
            raise CorrectionPackError("correction_pack_schema_invalid")
        return payload, {
            "kind": "supplied_file",
            "source_ref": str(path),
            "source_sha256": _sha256(path),
        }
    return {
        "schema_version": CORRECTION_PACK_SCHEMA,
        "project_id": project_id,
        "public_safe": True,
        "unsafe_ledger_bodies_reopened": False,
        "corrections": [],
    }, {"kind": "derived_empty", "source_ref": None}


def _text(value: object, error: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CorrectionPackError(error)
    return value.strip()


def _safe_ref(value: object, error: str) -> str:
    ref = _text(value, error)
    if ref.startswith("receipt:") or ref.startswith("thread:") or ref.startswith("artifact:"):
        return ref
    path = Path(ref)
    if path.is_absolute() or ".." in path.parts:
        raise CorrectionPackError(error)
    return ref


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
