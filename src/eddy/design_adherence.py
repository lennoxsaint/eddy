"""Static design-contract checks used before animation or contract revision."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


DESIGN_REQUIRED = {
    "schema": "schema_version: eddy-design-contract-v2",
    "normative": "normative: true",
    "video_scale": "frame_scale_required: true",
    "typography": "display_min_px_1080p:",
    "reading_grade": "maximum_reading_grade:",
    "layering": "required_layers: [background, midground, foreground]",
    "semantic_layouts": "semantic_layout_changes_only: true",
    "forbidden_moves": "## Forbidden moves",
}
LONG_REQUIRED = {
    "schema": "schema_version: eddy-frame-contract-v3",
    "orientation": "orientation: landscape",
    "resolution": 'resolution: "1920x1080"',
    "safe_zones": "safe_zones:",
    "caption_band": "caption_band:",
    "proof_collision": "proof_ui_collision_boundary_px:",
    "static_first": "hero_frame_static_approval_required: true",
    "caption_policy": "designed_long_captions: false",
    "semantic_zoom": "semantic_zoom_job_required: true",
    "motion_coverage": "motion_full_segment_coverage_required: true",
    "frozen_tail": "frozen_tail_allowed: false",
    "frame_flash": "one_frame_flash_allowed: false",
}
SHORT_REQUIRED = {
    "schema": "schema_version: eddy-frame-contract-v3",
    "orientation": "orientation: portrait",
    "resolution": 'resolution: "1080x1920"',
    "safe_zones": "safe_zones:",
    "caption_band": "caption_band:",
    "speaker_layout": "speaker_top_screen_bottom",
    "prior_words": "prior_words: visible",
    "active_word": "active_word: highlighted",
    "future_words": "future_words: invisible",
    "speaker_attribution": "speaker_attribution: color_plus_label",
    "motion_coverage": "motion_full_segment_coverage_required: true",
    "frozen_tail": "frozen_tail_allowed: false",
    "frame_flash": "one_frame_flash_allowed: false",
}


def validate_design_contract_texts(
    design: str,
    long_frame: str,
    short_frame: str,
) -> dict[str, Any]:
    checks = {
        "design": _surface_checks(design, DESIGN_REQUIRED),
        "long_frame": _surface_checks(long_frame, LONG_REQUIRED),
        "short_frame": _surface_checks(short_frame, SHORT_REQUIRED),
    }
    failures = [
        f"{surface}:{check}"
        for surface, rows in checks.items()
        for check, passed in rows.items()
        if not passed
    ]
    if failures:
        raise ValueError("design_adherence_failed:" + ",".join(failures))
    return {
        "schema_version": "eddy-design-adherence-v1",
        "pass": True,
        "checks": checks,
    }


def validate_design_contract_files(run_dir: Path) -> dict[str, Any]:
    paths = {
        "design": run_dir / "design.md",
        "long_frame": run_dir / "frame.md",
        "short_frame": run_dir / "shorts" / "frame.md",
    }
    for label, path in paths.items():
        if not path.is_file():
            raise ValueError(f"design_contract_missing:{label}")
    result = validate_design_contract_texts(
        paths["design"].read_text(),
        paths["long_frame"].read_text(),
        paths["short_frame"].read_text(),
    )
    result["files"] = {
        label: {
            "ref": path.relative_to(run_dir).as_posix(),
            "sha256": _sha256(path),
        }
        for label, path in paths.items()
    }
    return result


def _surface_checks(text: str, required: dict[str, str]) -> dict[str, bool]:
    return {label: marker in text for label, marker in required.items()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
