"""Machine-readable compatibility handshake for external Eddy orchestrators."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .professional_proof import (
    GATE_EVALUATORS,
    GATE_METRIC_REQUIREMENTS,
    REQUIRED_PROFESSIONAL_GATES_V2,
)
from .quality import PROFILE_FILES


def eddy_capabilities(canonical_root: Path) -> dict[str, Any]:
    """Declare supported public contracts without exposing editor/model identity."""

    root = canonical_root.resolve()
    profile_hashes = {
        profile_id: _sha256(root / relative)
        for profile_id, relative in sorted(PROFILE_FILES.items())
        if (root / relative).is_file()
    }
    return {
        "schema_version": "eddy-capabilities-v1",
        "product": "Eddy",
        "single_editor_only": True,
        "preferred_edit_plan_schema": "edit-plan-v3.7",
        "supported_edit_plan_schemas": [
            "edit-plan-v3",
            "edit-plan-v3.1",
            "edit-plan-v3.2",
            "edit-plan-v3.3",
            "edit-plan-v3.4",
            "edit-plan-v3.5",
            "edit-plan-v3.6",
            "edit-plan-v3.7",
        ],
        "host_packet_schema": "eddy-host-packet-v3.3",
        "contract_bundle_schema": "eddy-contract-bundle-v3",
        "project_fact_brief_schema": "eddy-project-fact-brief-v2",
        "correction_pack_schema": "eddy-correction-pack-v1",
        "professional_gate_schema": "professional-gate-evidence-v2",
        "verifier_review_schema": "verifier-review-v2",
        "opening_blueprint_delivery_schemas": [
            "eddy-opening-blueprint-delivery-v1",
            "eddy-opening-blueprint-delivery-v2",
        ],
        "opening_blueprint_optional": True,
        "long_routes": {"default": 3, "minimum": 3, "maximum": 6},
        "shorts": {"minimum": 3, "maximum": 5},
        "shared_body_required": True,
        "quality_profile_hashes": profile_hashes,
        "professional_gates": {
            "required": sorted(REQUIRED_PROFESSIONAL_GATES_V2),
            "evaluators": dict(sorted(GATE_EVALUATORS.items())),
            "metric_requirements": {
                gate_id: GATE_METRIC_REQUIREMENTS[gate_id]
                for gate_id in sorted(GATE_METRIC_REQUIREMENTS)
            },
            "generic_evidence_reuse_allowed": False,
            "self_attested_clearance_allowed": False,
        },
        "cut_boundary_contract": {
            "micro_insert_frames": [1, 6],
            "silent_handle_max_seconds": 0.24,
            "silent_handle_max_dbfs": -40,
            "frame_window_each_side": 8,
            "supercut_speed": 0.25,
            "decoder_policy": "fps_mode_passthrough",
            "protected_insert_evidence": {
                "relative_ref_required": True,
                "sha256_required": True,
                "purpose_specific": True,
                "self_attested": False,
            },
        },
    }


def validate_capabilities(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != "eddy-capabilities-v1":
        raise ValueError("eddy_capabilities_schema_invalid")
    if value.get("preferred_edit_plan_schema") not in value.get(
        "supported_edit_plan_schemas", []
    ):
        raise ValueError("eddy_capabilities_preferred_schema_unsupported")
    routes = value.get("long_routes")
    if not isinstance(routes, dict) or routes != {"default": 3, "minimum": 3, "maximum": 6}:
        raise ValueError("eddy_capabilities_long_routes_invalid")
    gates = value.get("professional_gates")
    if (
        not isinstance(gates, dict)
        or set(gates.get("required", [])) != REQUIRED_PROFESSIONAL_GATES_V2
        or gates.get("evaluators") != GATE_EVALUATORS
        or gates.get("metric_requirements") != GATE_METRIC_REQUIREMENTS
        or gates.get("generic_evidence_reuse_allowed") is not False
        or gates.get("self_attested_clearance_allowed") is not False
    ):
        raise ValueError("eddy_capabilities_professional_gates_invalid")
    return dict(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
