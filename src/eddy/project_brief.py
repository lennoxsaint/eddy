"""Typed, hash-bound project facts for owner-profile video edits."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


PROJECT_FACT_BRIEF_SCHEMA = "eddy-project-fact-brief-v2"
PROJECT_FACT_BRIEF_LEGACY_SCHEMA = "eddy-project-fact-brief-v1"


class ProjectFactBriefError(ValueError):
    """A project fact brief is missing required truth or contains unsafe references."""


def materialize_project_fact_brief(
    run_dir: Path,
    *,
    source: Path,
    explicit: str | Path | dict[str, Any] | None = None,
    preferred_schema: str = PROJECT_FACT_BRIEF_SCHEMA,
) -> dict[str, Any]:
    """Validate a supplied brief or create a restrictive project-local default."""

    if preferred_schema not in {PROJECT_FACT_BRIEF_SCHEMA, PROJECT_FACT_BRIEF_LEGACY_SCHEMA}:
        raise ProjectFactBriefError("project_fact_brief_preferred_schema_invalid")
    payload, provenance = _load_or_derive(source, explicit, preferred_schema=preferred_schema)
    normalized = validate_project_fact_brief(payload)
    output = run_dir / "project-fact-brief.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    return {
        "schema_version": (
            "eddy-project-fact-brief-ref-v2"
            if normalized["schema_version"] == PROJECT_FACT_BRIEF_SCHEMA
            else "eddy-project-fact-brief-ref-v1"
        ),
        "path": str(output),
        "ref": output.relative_to(run_dir).as_posix(),
        "sha256": _sha256(output),
        "project_id": normalized["project_id"],
        "status": normalized["status"],
        "provenance": provenance,
    }


def validate_project_fact_brief(value: object) -> dict[str, Any]:
    """Fail closed on unsupported, unverified, or path-escaping project facts."""

    if not isinstance(value, dict) or value.get("schema_version") not in {
        PROJECT_FACT_BRIEF_SCHEMA,
        PROJECT_FACT_BRIEF_LEGACY_SCHEMA,
    }:
        raise ProjectFactBriefError("project_fact_brief_schema_invalid")
    schema_version = str(value["schema_version"])
    project_id = value.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ProjectFactBriefError("project_fact_project_id_required")
    if value.get("status") not in {"verified", "derived_restrictive"}:
        raise ProjectFactBriefError("project_fact_status_invalid")

    people = _list_of_dicts(value.get("people"), "project_fact_people_invalid")
    for person in people:
        _required_text(person, "id", "project_fact_person_id_required")
        _required_text(person, "display_name", "project_fact_person_name_required")
        _source_refs(person.get("source_refs"), "project_fact_person_source_refs_invalid")

    facts = _list_of_dicts(value.get("facts"), "project_fact_facts_invalid")
    fact_ids: set[str] = set()
    for fact in facts:
        fact_id = _required_text(fact, "id", "project_fact_id_required")
        if fact_id in fact_ids:
            raise ProjectFactBriefError(f"project_fact_id_duplicated:{fact_id}")
        fact_ids.add(fact_id)
        required = fact.get("required")
        if not isinstance(required, bool):
            raise ProjectFactBriefError(f"project_fact_required_flag_invalid:{fact_id}")
        value_present = fact.get("value") not in {None, ""}
        refs = _source_refs(
            fact.get("source_refs"),
            f"project_fact_source_refs_invalid:{fact_id}",
        )
        if required and (not value_present or not refs):
            raise ProjectFactBriefError(f"project_fact_required_missing:{fact_id}")
        if value_present and not refs:
            raise ProjectFactBriefError(f"project_fact_unverified:{fact_id}")

    brand = value.get("brand")
    if not isinstance(brand, dict):
        raise ProjectFactBriefError("project_fact_brand_invalid")
    tokens = brand.get("tokens")
    if not isinstance(tokens, dict):
        raise ProjectFactBriefError("project_fact_brand_tokens_invalid")
    for key, token in tokens.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(token, str):
            raise ProjectFactBriefError("project_fact_brand_token_invalid")
    _source_refs(brand.get("asset_refs"), "project_fact_brand_asset_refs_invalid")

    ui_surfaces = _list_of_dicts(
        value.get("ui_surfaces"),
        "project_fact_ui_surfaces_invalid",
    )
    for surface in ui_surfaces:
        surface_id = _required_text(
            surface,
            "id",
            "project_fact_ui_surface_id_required",
        )
        if surface.get("evidence_kind") not in {"capture", "reconstructed"}:
            raise ProjectFactBriefError(
                f"project_fact_ui_evidence_kind_invalid:{surface_id}"
            )
        refs = _source_refs(
            surface.get("source_refs"),
            f"project_fact_ui_source_refs_invalid:{surface_id}",
        )
        bindings = surface.get("factual_bindings")
        if not isinstance(bindings, list) or not all(
            isinstance(item, str) and item in fact_ids for item in bindings
        ):
            raise ProjectFactBriefError(
                f"project_fact_ui_bindings_invalid:{surface_id}"
            )
        if surface["evidence_kind"] == "reconstructed" and (not refs or not bindings):
            raise ProjectFactBriefError(
                f"project_fact_reconstruction_unbound:{surface_id}"
            )

    output = value.get("output")
    if not isinstance(output, dict) or not isinstance(output.get("long_captions"), bool):
        raise ProjectFactBriefError("project_fact_output_invalid")
    runtime = output.get("runtime_target_seconds")
    if runtime is not None and (
        not isinstance(runtime, (int, float)) or isinstance(runtime, bool) or runtime <= 0
    ):
        raise ProjectFactBriefError("project_fact_runtime_target_invalid")
    if schema_version == PROJECT_FACT_BRIEF_SCHEMA:
        routes = _list_of_dicts(
            output.get("long_routes"),
            "project_fact_long_routes_invalid",
        )
        if not 3 <= len(routes) <= 6:
            raise ProjectFactBriefError("project_fact_long_routes_count_invalid")
        route_ids: list[str] = []
        primary_count = 0
        for index, route in enumerate(routes, start=1):
            route_id = _required_text(
                route,
                "id",
                "project_fact_long_route_id_required",
            )
            _required_text(
                route,
                "label",
                f"project_fact_long_route_label_required:{route_id}",
            )
            if route.get("required") is not True:
                raise ProjectFactBriefError(
                    f"project_fact_long_route_required_flag_invalid:{route_id}"
                )
            if route.get("rank") != index:
                raise ProjectFactBriefError(
                    f"project_fact_long_route_rank_invalid:{route_id}"
                )
            primary = route.get("primary", False)
            if not isinstance(primary, bool):
                raise ProjectFactBriefError(
                    f"project_fact_long_route_primary_invalid:{route_id}"
                )
            primary_count += int(primary)
            route_ids.append(route_id)
        if len(set(route_ids)) != len(route_ids):
            raise ProjectFactBriefError("project_fact_long_route_ids_duplicated")
        if primary_count != 1:
            raise ProjectFactBriefError("project_fact_one_primary_long_route_required")

    audio = value.get("audio")
    if not isinstance(audio, dict) or audio.get("studio_sound_required") is not True:
        raise ProjectFactBriefError("project_fact_studio_sound_required")
    for key in ("studio_sound_ref", "authorized_treatment_route"):
        if key in audio and audio[key] not in {None, ""}:
            if not isinstance(audio[key], str):
                raise ProjectFactBriefError(f"project_fact_audio_{key}_invalid")
            if key.endswith("_ref"):
                _safe_ref(audio[key], f"project_fact_audio_{key}_invalid")
    if schema_version == PROJECT_FACT_BRIEF_SCHEMA:
        roles = _list_of_dicts(
            audio.get("source_audio_roles"),
            "project_fact_source_audio_roles_invalid",
        )
        role_ids: set[str] = set()
        for row in roles:
            role_id = _required_text(
                row,
                "id",
                "project_fact_source_audio_role_id_required",
            )
            if role_id in role_ids:
                raise ProjectFactBriefError(
                    f"project_fact_source_audio_role_duplicated:{role_id}"
                )
            role_ids.add(role_id)
            if row.get("role") not in {
                "authoritative_dialogue",
                "system_response",
                "non_authoritative",
            }:
                raise ProjectFactBriefError(
                    f"project_fact_source_audio_role_invalid:{role_id}"
                )
            _safe_ref(
                _required_text(
                    row,
                    "source_ref",
                    f"project_fact_source_audio_ref_required:{role_id}",
                ),
                f"project_fact_source_audio_ref_invalid:{role_id}",
            )
            intervals = row.get("required_intervals", [])
            if not isinstance(intervals, list):
                raise ProjectFactBriefError(
                    f"project_fact_source_audio_intervals_invalid:{role_id}"
                )
            for interval in intervals:
                if (
                    not isinstance(interval, list)
                    or len(interval) != 2
                    or not all(isinstance(point, (int, float)) for point in interval)
                    or float(interval[0]) < 0
                    or float(interval[1]) <= float(interval[0])
                ):
                    raise ProjectFactBriefError(
                        f"project_fact_source_audio_intervals_invalid:{role_id}"
                    )

    protected = _list_of_dicts(
        value.get("protected_moments"),
        "project_fact_protected_moments_invalid",
    )
    for row in protected:
        try:
            start, end = float(row["start"]), float(row["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjectFactBriefError("project_fact_protected_range_invalid") from exc
        if start < 0 or end <= start:
            raise ProjectFactBriefError("project_fact_protected_range_invalid")
        _required_text(row, "reason", "project_fact_protected_reason_required")

    return {
        "schema_version": schema_version,
        "project_id": project_id.strip(),
        "status": value["status"],
        "people": people,
        "facts": facts,
        "brand": brand,
        "ui_surfaces": ui_surfaces,
        "output": dict(output),
        "audio": dict(audio),
        "protected_moments": protected,
    }


def _load_or_derive(
    source: Path,
    explicit: str | Path | dict[str, Any] | None,
    *,
    preferred_schema: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(explicit, dict):
        return dict(explicit), {"kind": "inline", "source_ref": None}
    candidate: Path | None = None
    if isinstance(explicit, (str, Path)):
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.is_file():
            raise ProjectFactBriefError(f"project_fact_brief_missing:{candidate}")
    else:
        root = source.parent if source.is_file() else source
        discovered = root / "project-fact-brief.json"
        if discovered.is_file():
            candidate = discovered
    if candidate is not None:
        try:
            payload = json.loads(candidate.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectFactBriefError(f"project_fact_brief_invalid:{candidate}") from exc
        if not isinstance(payload, dict):
            raise ProjectFactBriefError("project_fact_brief_schema_invalid")
        return payload, {
            "kind": "supplied_file",
            "source_ref": str(candidate),
            "source_sha256": _sha256(candidate),
        }
    project_id = source.stem if source.is_file() else source.name
    payload = {
        "schema_version": preferred_schema,
        "project_id": project_id or "untitled-project",
        "status": "derived_restrictive",
        "people": [],
        "facts": [],
        "brand": {"tokens": {}, "asset_refs": []},
        "ui_surfaces": [],
        "output": {
            "long_captions": False,
            "long_routes": [
                {
                    "id": "primary",
                    "label": "Primary",
                    "rank": 1,
                    "required": True,
                    "primary": True,
                },
                {
                    "id": "alternate-a",
                    "label": "Alternate A",
                    "rank": 2,
                    "required": True,
                    "primary": False,
                },
                {
                    "id": "alternate-b",
                    "label": "Alternate B",
                    "rank": 3,
                    "required": True,
                    "primary": False,
                },
            ],
        },
        "audio": {"studio_sound_required": True, "source_audio_roles": []},
        "protected_moments": [],
    }
    if preferred_schema == PROJECT_FACT_BRIEF_LEGACY_SCHEMA:
        payload["output"] = {"long_captions": False}
        payload["audio"] = {"studio_sound_required": True}
    return payload, {"kind": "derived_restrictive", "source_ref": None}


def _list_of_dicts(value: object, error: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ProjectFactBriefError(error)
    return [dict(item) for item in value]


def _required_text(row: dict[str, Any], key: str, error: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProjectFactBriefError(error)
    return value.strip()


def _source_refs(value: object, error: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProjectFactBriefError(error)
    for raw in value:
        _safe_ref(raw, error)
    return list(value)


def _safe_ref(raw: str, error: str) -> None:
    if not raw.strip():
        raise ProjectFactBriefError(error)
    if ":" in raw and not raw.startswith(("/", "./", "../")):
        return
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ProjectFactBriefError(error)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
