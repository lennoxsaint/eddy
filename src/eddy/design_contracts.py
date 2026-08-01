"""Create and maintain run-local HyperFrames design contracts."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .design_adherence import (
    validate_design_contract_files,
    validate_design_contract_texts,
)
from .project_brief import materialize_project_fact_brief


HYPERFRAMES_VERSION = "0.7.3"
HYPERFRAMES_COMMIT = "997823b6b523eb4d43e0f03c140f5897f13ce780"
HYPERFRAMES_REFERENCES = {
    "design-spec.md": "2287b88dab08bbbab4314e52f2770f34f6937e6eb69d37249c6b6fa8e1339d13",
    "house-style.md": "61e260aebcab552dcd42fd2dcaf4431349b51f043fe155c8f670f156d09b69dd",
    "video-composition.md": "6aae0bc1e79e9e8c1451ced986b5bbb4d59680c94276a299b6ecf67e3f440b09",
    "design-adherence.md": "ff21deb80143c8e09092958a6f40bc712173a43d23c5ea88742566573a2a7241",
}


class DesignContractError(ValueError):
    """A run-local design contract cannot be created or maintained safely."""


def create_contract_bundle(
    run_dir: Path,
    *,
    source: Path,
    canonical_root: Path,
    profile: dict[str, Any],
    profile_path: Path,
    source_hashes: dict[str, str],
    project_fact_brief: dict[str, Any] | None = None,
    hyperframes_root: Path | None = None,
) -> dict[str, Any]:
    """Create design.md, both frame contracts, doctrine snapshots, and the bundle."""

    run_dir = run_dir.resolve()
    if project_fact_brief is None:
        project_fact_brief = materialize_project_fact_brief(
            run_dir,
            source=source,
        )
    contracts = run_dir / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    brand = _discover_brand_contract(source, project_fact_brief=project_fact_brief)
    design_path = run_dir / "design.md"
    long_frame_path = run_dir / "frame.md"
    short_frame_path = run_dir / "shorts" / "frame.md"
    short_frame_path.parent.mkdir(parents=True, exist_ok=True)
    if not design_path.exists():
        design_path.write_text(_design_markdown(profile, brand))
    if not long_frame_path.exists():
        long_frame_path.write_text(_frame_markdown(profile, portrait=False))
    if not short_frame_path.exists():
        short_frame_path.write_text(_frame_markdown(profile, portrait=True))
    adherence_path = contracts / "design-adherence.json"
    _write_json(adherence_path, validate_design_contract_files(run_dir))

    doctrine_manifest = _snapshot_hyperframes(
        contracts,
        canonical_root=canonical_root,
        hyperframes_root=hyperframes_root,
    )
    rubric_path = canonical_root / "evals" / "professional-youtube-100-rubric.json"
    corrections_name = (
        "professional-youtube-corrections-v2.json"
        if profile.get("id") == "lennox-professional-youtube-v2"
        else "professional-youtube-corrections-v1.json"
    )
    corrections_path = canonical_root / "evals" / corrections_name
    verifier_path = canonical_root / "references" / "verifier-review-contract.json"
    if not rubric_path.is_file() or not corrections_path.is_file() or not verifier_path.is_file():
        raise DesignContractError("quality_evidence_surface_missing")
    quality_dir = contracts / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)
    profile_snapshot = quality_dir / "profile.json"
    rubric_snapshot = quality_dir / "professional-youtube-100-rubric.json"
    corrections_snapshot = quality_dir / corrections_name
    verifier_snapshot = quality_dir / "verifier-review-contract.json"
    shutil.copy2(profile_path, profile_snapshot)
    shutil.copy2(rubric_path, rubric_snapshot)
    shutil.copy2(corrections_path, corrections_snapshot)
    shutil.copy2(verifier_path, verifier_snapshot)
    source_lock_path = run_dir / "source-lock.json"
    bundle = {
        "schema_version": "eddy-contract-bundle-v2",
        "created_at": datetime.now(UTC).isoformat(),
        "profile": {
            "id": profile["id"],
            "schema_version": profile["schema_version"],
            "ref": profile_snapshot.relative_to(run_dir).as_posix(),
            "sha256": _sha256(profile_snapshot),
            "source_ref": profile_path.relative_to(canonical_root).as_posix(),
        },
        "precedence": [
            "current_run_instruction",
            "supplied_project_brand",
            "lennox_editing_taste_profile",
            "hyperframes_house_style",
        ],
        "design_contracts": {
            "design": _entry(run_dir, design_path, revision=1),
            "long_frame": _entry(run_dir, long_frame_path, revision=1),
            "short_frame": _entry(run_dir, short_frame_path, revision=1),
        },
        "project_fact_brief": _project_fact_entry(
            run_dir,
            project_fact_brief,
        ),
        "hyperframes": doctrine_manifest,
        "quality_evidence": {
            "rubric": {
                "ref": rubric_snapshot.relative_to(run_dir).as_posix(),
                "sha256": _sha256(rubric_snapshot),
                "source_ref": rubric_path.relative_to(canonical_root).as_posix(),
            },
            "correction_evals": {
                "ref": corrections_snapshot.relative_to(run_dir).as_posix(),
                "sha256": _sha256(corrections_snapshot),
                "source_ref": corrections_path.relative_to(canonical_root).as_posix(),
            },
            "verifier_contract": {
                "ref": verifier_snapshot.relative_to(run_dir).as_posix(),
                "sha256": _sha256(verifier_snapshot),
                "source_ref": verifier_path.relative_to(canonical_root).as_posix(),
            },
            "design_adherence": {
                "ref": adherence_path.relative_to(run_dir).as_posix(),
                "sha256": _sha256(adherence_path),
            },
        },
        "source_lock": {
            "ref": "source-lock.json",
            "sha256": _sha256(source_lock_path),
            "source_hashes": source_hashes,
        },
        "brand_evidence": brand,
        "audio_policy": {
            "sources": ["local", "supplied", "bundled", "locally_generated"],
            "paid_retrieval_without_approval": False,
            "provenance_required": True,
            "studio_sound_required": True,
            "studio_sound_lineage_policy": "verified_descript_only",
            "shorts_music_policy": "purposeful_variation",
        },
        "review_policy": {
            "verifier_authority": "independent_no_edit_context",
            "verifier_edit_authority": False,
            "repair_review": "repaired_intervals_and_joins_plus_full_final",
            "promotion_state": "proof_gated_candidate_awaiting_owner_taste",
            "open_items": "objective_closed_subjective_optional",
        },
        "revision_history": [],
    }
    bundle_path = contracts / "contract-bundle.json"
    _write_json(bundle_path, bundle)
    return {
        "schema_version": "eddy-contract-bundle-ref-v2",
        "path": str(bundle_path),
        "ref": bundle_path.relative_to(run_dir).as_posix(),
        "sha256": _sha256(bundle_path),
        "profile_id": profile["id"],
        "design_contracts": bundle["design_contracts"],
    }


def revise_contract_bundle(
    run_dir: Path,
    *,
    reason: str,
    design_markdown: str | None = None,
    long_frame_markdown: str | None = None,
    short_frame_markdown: str | None = None,
) -> dict[str, Any]:
    """Version a systemic design repair and invalidate dependent render evidence."""

    if not reason.strip():
        raise DesignContractError("design_contract_revision_reason_required")
    updates = {
        "design": (run_dir / "design.md", design_markdown),
        "long_frame": (run_dir / "frame.md", long_frame_markdown),
        "short_frame": (run_dir / "shorts" / "frame.md", short_frame_markdown),
    }
    changed = {key: row for key, row in updates.items() if row[1] is not None}
    if not changed:
        raise DesignContractError("design_contract_revision_content_required")
    proposed = {
        key: str(content) if content is not None else path.read_text()
        for key, (path, content) in updates.items()
    }
    try:
        validate_design_contract_texts(
            proposed["design"],
            proposed["long_frame"],
            proposed["short_frame"],
        )
    except ValueError as exc:
        raise DesignContractError(str(exc)) from exc
    bundle_path = run_dir / "contracts" / "contract-bundle.json"
    if not bundle_path.is_file():
        raise DesignContractError("contract_bundle_missing")
    bundle = json.loads(bundle_path.read_text())
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    history_dir = run_dir / "contracts" / "history" / stamp
    history_dir.mkdir(parents=True, exist_ok=False)
    revision_row: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "reason": reason.strip(),
        "contracts": {},
    }
    for key, (path, content) in changed.items():
        assert content is not None
        old = bundle["design_contracts"][key]
        destination = history_dir / path.relative_to(run_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        path.write_text(content.rstrip() + "\n")
        revision = int(old["revision"]) + 1
        bundle["design_contracts"][key] = _entry(run_dir, path, revision=revision)
        revision_row["contracts"][key] = {
            "from_revision": old["revision"],
            "from_sha256": old["sha256"],
            "to_revision": revision,
            "to_sha256": bundle["design_contracts"][key]["sha256"],
        }
    bundle["revision_history"].append(revision_row)
    adherence_path = run_dir / "contracts" / "design-adherence.json"
    _write_json(adherence_path, validate_design_contract_files(run_dir))
    bundle["quality_evidence"]["design_adherence"] = {
        "ref": adherence_path.relative_to(run_dir).as_posix(),
        "sha256": _sha256(adherence_path),
    }
    _write_json(bundle_path, bundle)
    invalidation = {
        "schema_version": "eddy-render-invalidation-v1",
        "reason": reason.strip(),
        "contract_bundle_sha256": _sha256(bundle_path),
        "dependent_renders_invalidated": True,
        "required_checks": [
            "hyperframes_validate",
            "hyperframes_strict_inspect",
            "design_adherence",
            "contrast",
            "animation_map_review",
        ],
    }
    _write_json(run_dir / "contracts" / "render-invalidation.json", invalidation)
    return {
        "schema_version": "eddy-contract-bundle-ref-v2",
        "path": str(bundle_path),
        "ref": bundle_path.relative_to(run_dir).as_posix(),
        "sha256": _sha256(bundle_path),
        "profile_id": bundle["profile"]["id"],
        "design_contracts": bundle["design_contracts"],
        "invalidation": invalidation,
    }


def _discover_brand_contract(
    source: Path,
    *,
    project_fact_brief: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(project_fact_brief, dict):
        raw_path = project_fact_brief.get("path")
        if isinstance(raw_path, str):
            candidate = Path(raw_path)
            if candidate.is_file():
                brief_payload = json.loads(candidate.read_text())
                project_tokens = (brief_payload.get("brand") or {}).get("tokens")
                if isinstance(project_tokens, dict) and project_tokens:
                    return {
                        "status": "supplied_project_fact_brief",
                        "path": project_fact_brief.get("ref"),
                        "sha256": project_fact_brief.get("sha256"),
                        "name": "project-fact-brief.json",
                        "tokens": project_tokens,
                    }
    if source.is_file():
        roots = (source.parent,)
    else:
        roots = (source,)
    candidates = ("design.md", "DESIGN.md", "brand.json", "brand-tokens.json", "tokens.json")
    for root in roots:
        for name in candidates:
            path = root / name
            if path.is_file():
                tokens: dict[str, Any] = {}
                if path.suffix == ".json":
                    try:
                        raw = json.loads(path.read_text())
                    except (json.JSONDecodeError, OSError):
                        raw = {}
                    if isinstance(raw, dict):
                        candidate_tokens = raw.get("tokens", raw)
                        if isinstance(candidate_tokens, dict):
                            tokens = candidate_tokens
                return {
                    "status": "supplied",
                    "path": name,
                    "sha256": _sha256(path),
                    "name": name,
                    "tokens": tokens,
                }
    return {
        "status": "profile_default_pending_host_enrichment",
        "path": None,
        "sha256": None,
        "name": None,
        "tokens": {},
    }


def _design_markdown(profile: dict[str, Any], brand: dict[str, Any]) -> str:
    raw_profile_tokens = profile.get("design_defaults")
    profile_tokens: dict[str, Any] = (
        raw_profile_tokens if isinstance(raw_profile_tokens, dict) else {}
    )
    raw_brand_tokens = brand.get("tokens")
    brand_tokens: dict[str, Any] = (
        raw_brand_tokens if isinstance(raw_brand_tokens, dict) else {}
    )
    accent = str(
        brand_tokens.get("accent", profile_tokens.get("accent", "#7C5CFF"))
    )
    background = str(
        brand_tokens.get("background", profile_tokens.get("background", "#0E1014"))
    )
    foreground = str(
        brand_tokens.get("foreground", profile_tokens.get("foreground", "#F7F8FA"))
    )
    return f"""---
schema_version: eddy-design-contract-v2
revision: 1
normative: true
brand_evidence_status: {brand["status"]}
colors:
  background: "{background}"
  foreground: "{foreground}"
  accent: "{accent}"
typography:
  display_min_px_1080p: 72
  body_min_px_1080p: 40
  caption_min_px_1080p: 54
  minimum_reading_grade: 3
  maximum_reading_grade: 5
spacing:
  base_unit_px: 8
corners:
  panel_radius_px: 28
depth:
  required_layers: [background, midground, foreground]
composition:
  minimum_focal_points: 2
  frame_scale_required: true
  semantic_layout_changes_only: true
---

# Project design contract

The YAML frontmatter is normative. This prose explains intent.

## Visual thesis

Make the spoken idea easier to understand than talking head alone. Prefer real proof, then diagrams,
icons, spatial relationships, and mental models. Keep authored text sparse, active, factual, and
subordinate to the visual explanation.

## Brand precedence

Current run instruction wins, then supplied project brand, then the selected editing/taste profile,
then HyperFrames house style. A supplied brand source is recorded in the contract bundle.

## Forbidden moves

- Decorative motion without a communication job.
- Automated camera drift or filler punch-ins.
- Tiny product previews, obstructed proof, duplicate captions, or unreadable UI.
- Unsupported claims, fake product proof, excessive prose, and unlicensed media.
- Generic web-page card grids, lazy gradients, repeated centered stacks, or low-contrast decoration.

## Maintenance

Systemic design repairs increment this contract revision, record the exact reason and hash diff,
invalidate dependent renders, and rerun design-adherence checks. Project taste is never promoted
globally without owner approval.
"""


def _frame_markdown(profile: dict[str, Any], *, portrait: bool) -> str:
    if portrait:
        resolution = "1080x1920"
        safe = "{ top: 160, right: 72, bottom: 300, left: 72 }"
        caption = "{ y_min: 780, y_max: 1460 }"
        grammar = (
            "speaker_top_screen_bottom, speaker_full, proof_canvas, "
            "speaker_plus_mental_model"
        )
        title = "Portrait Short"
        caption_policy = """designed_short_captions: true
designed_long_captions: false
caption_policy:
  prior_words: visible
  active_word: highlighted
  future_words: invisible
  speaker_attribution: color_plus_label
  speaker_colors: design_contract_accessible_palette
  source_caption_collision: suppress_eddy_captions"""
    else:
        resolution = "1920x1080"
        safe = "{ top: 72, right: 88, bottom: 96, left: 88 }"
        caption = "{ y_min: 840, y_max: 1000 }"
        grammar = (
            "speaker_full, speaker_close, speaker_tight, pip_bottom_right, pip_bottom_left, "
            "pip_top_right, pip_top_left, "
            "vertical_speaker_left, vertical_speaker_right, embedded_split_left, "
            "embedded_split_right, speaker_plus_mental_model, proof_canvas"
        )
        title = "Landscape Long"
        caption_policy = """designed_long_captions: false
long_caption_override: project_fact_brief_only
caption_policy:
  source_caption_collision: suppress_eddy_captions"""
    return f"""---
schema_version: eddy-frame-contract-v3
revision: 1
normative: true
orientation: {"portrait" if portrait else "landscape"}
resolution: "{resolution}"
safe_zones: {safe}
caption_band: {caption}
layout_grammar: [{grammar}]
proof_ui_collision_boundary_px: 32
hero_frame_static_approval_required: true
animation_after_static_approval: true
semantic_transition_reason_required: true
semantic_zoom_job_required: true
motion_full_segment_coverage_required: true
frozen_tail_allowed: false
one_frame_flash_allowed: false
{caption_policy}
---

# {title} frame contract

## Hero-frame rule

Build and inspect every hero frame as a static composition before animation. Animation may reveal,
connect, compare, focus, or change state; it may not decorate a weak frame.

## Layout rule

Talking head is the human anchor. Screen recording is the authority for real product action and
proof. HyperFrames mental models take over when a concept, relationship, or result is clearer than
the recording. Every layout change needs a semantic reason.

## Collision and legibility

Protect readable UI, faces, captions, and proof targets. Respect the normative safe zones and
caption band. Reject tiny previews, overlay collisions, excessive text, and mobile-illegible detail.

## Captions

Designed captions are disabled for Longs unless the Project Fact Brief opts in. Shorts keep prior
words visible, highlight only the active word, hide every future word, and use stable accessible
speaker colors plus concise labels. Suppress Eddy captions when readable source captions exist.
"""


def _project_fact_entry(
    run_dir: Path,
    value: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DesignContractError("project_fact_brief_required")
    ref = value.get("ref")
    if not isinstance(ref, str):
        raise DesignContractError("project_fact_brief_ref_invalid")
    path = run_dir / ref
    if not path.is_file() or _sha256(path) != value.get("sha256"):
        raise DesignContractError("project_fact_brief_hash_mismatch")
    return {
        "schema_version": value.get("schema_version"),
        "ref": ref,
        "sha256": value["sha256"],
        "project_id": value.get("project_id"),
        "status": value.get("status"),
        "provenance": value.get("provenance"),
    }


def _snapshot_hyperframes(
    contracts: Path,
    *,
    canonical_root: Path,
    hyperframes_root: Path | None,
) -> dict[str, Any]:
    destination = contracts / "hyperframes"
    destination.mkdir(parents=True, exist_ok=True)
    source_root = hyperframes_root or Path.home() / "Developer" / "hyperframes"
    rows: dict[str, dict[str, str]] = {}
    for name, expected in HYPERFRAMES_REFERENCES.items():
        source = source_root / "skills" / "hyperframes-creative" / "references" / name
        if not source.is_file():
            fallback = canonical_root / "references" / "hyperframes-v0.7.3" / name
            source = fallback
        if not source.is_file():
            raise DesignContractError(f"hyperframes_reference_missing:{name}")
        actual = _sha256(source)
        if actual != expected:
            raise DesignContractError(f"hyperframes_reference_hash_mismatch:{name}")
        target = destination / name
        shutil.copy2(source, target)
        rows[name] = {
            "ref": target.relative_to(contracts.parent).as_posix(),
            "sha256": actual,
        }
    manifest = {
        "version": HYPERFRAMES_VERSION,
        "commit": HYPERFRAMES_COMMIT,
        "references": rows,
        "copy_policy": "run_local_no_hotlinks",
    }
    _write_json(contracts / "hyperframes-reference-manifest.json", manifest)
    return manifest


def _entry(run_dir: Path, path: Path, *, revision: int) -> dict[str, Any]:
    return {
        "ref": path.relative_to(run_dir).as_posix(),
        "sha256": _sha256(path),
        "revision": revision,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
