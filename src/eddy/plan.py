"""Validated host-authored edit plans for the thin Eddy runtime."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


class PlanValidationError(ValueError):
    """The host plan violates the public Eddy v3 contract."""


@dataclass(frozen=True, slots=True)
class BodyPlan:
    keep: tuple[tuple[float, float], ...]
    drop: tuple[tuple[float, float], ...]
    retake_groups: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class HookPlan:
    id: str
    rank: int
    segments: tuple[tuple[float, float], ...]
    proof_assets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EditPlanV3:
    schema_version: str
    source_hashes: dict[str, str]
    protected: tuple[dict[str, Any], ...]
    body: BodyPlan
    hooks: tuple[HookPlan, HookPlan, HookPlan]
    shorts: tuple[dict[str, Any], ...]
    motion_beats: tuple[dict[str, Any], ...]

    @property
    def primary_hook(self) -> HookPlan:
        return self.hooks[0]

    @property
    def alternate_hooks(self) -> tuple[HookPlan, HookPlan]:
        return self.hooks[1:]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EditPlanV3":
        allowed = {
            "schema_version",
            "source_hashes",
            "protected",
            "body",
            "hooks",
            "shorts",
            "motion_beats",
        }
        extra = sorted(set(payload) - allowed)
        if extra:
            raise PlanValidationError(f"unsupported_edit_plan_fields:{','.join(extra)}")
        if payload.get("schema_version") != "edit-plan-v3":
            raise PlanValidationError("edit_plan_schema_version_invalid")

        raw_hooks = payload.get("hooks")
        if not isinstance(raw_hooks, list) or len(raw_hooks) != 3:
            raise PlanValidationError("three_ranked_hooks_required")
        hooks = tuple(_parse_hook(item) for item in raw_hooks)
        if tuple(hook.rank for hook in hooks) != (1, 2, 3):
            raise PlanValidationError("hook_ranks_must_be_1_2_3")
        if len({hook.id for hook in hooks}) != 3:
            raise PlanValidationError("hook_ids_must_be_unique")

        raw_body = payload.get("body")
        if not isinstance(raw_body, dict):
            raise PlanValidationError("shared_body_required")
        body = BodyPlan(
            keep=_ranges(raw_body.get("keep"), "body_keep"),
            drop=_ranges(raw_body.get("drop", []), "body_drop"),
            retake_groups=_dict_sequence(raw_body.get("retake_groups", []), "retake_groups"),
        )
        if not body.keep:
            raise PlanValidationError("shared_body_keep_required")

        hashes = payload.get("source_hashes")
        if not isinstance(hashes, dict) or not hashes:
            raise PlanValidationError("source_hashes_required")
        if not all(isinstance(key, str) and _valid_hash(value) for key, value in hashes.items()):
            raise PlanValidationError("source_hash_invalid")

        shorts = payload.get("shorts", [])
        if not isinstance(shorts, list) or not 3 <= len(shorts) <= 5:
            raise PlanValidationError("shorts_count_must_be_3_to_5")
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not _ranges(item.get("segments"), "short_segments")
            for item in shorts
        ):
            raise PlanValidationError("short_candidate_invalid")
        short_ids = [str(item["id"]).strip() for item in shorts]
        if any(not short_id for short_id in short_ids) or len(set(short_ids)) != len(short_ids):
            raise PlanValidationError("short_ids_must_be_unique")

        protected = _dict_sequence(payload.get("protected", []), "protected")
        for item in protected:
            try:
                start, end = float(item["start"]), float(item["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise PlanValidationError("protected_range_invalid") from exc
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
                raise PlanValidationError("protected_range_invalid")
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                raise PlanValidationError("protected_reason_required")

        motion_beats = _dict_sequence(payload.get("motion_beats", []), "motion_beats")

        return cls(
            schema_version="edit-plan-v3",
            source_hashes=dict(hashes),
            protected=protected,
            body=body,
            hooks=hooks,  # type: ignore[arg-type]
            shorts=tuple(shorts),
            motion_beats=motion_beats,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_hashes": self.source_hashes,
            "protected": list(self.protected),
            "body": {
                "keep": [list(item) for item in self.body.keep],
                "drop": [list(item) for item in self.body.drop],
                "retake_groups": list(self.body.retake_groups),
            },
            "hooks": [
                {
                    "id": hook.id,
                    "rank": hook.rank,
                    "segments": [list(item) for item in hook.segments],
                    "proof_assets": list(hook.proof_assets),
                }
                for hook in self.hooks
            ],
            "shorts": list(self.shorts),
            "motion_beats": list(self.motion_beats),
        }


def _valid_hash(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value.lower())


def _ranges(value: object, label: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list):
        raise PlanValidationError(f"{label}_ranges_required")
    parsed: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise PlanValidationError(f"{label}_range_invalid")
        try:
            start, end = float(item[0]), float(item[1])
        except (TypeError, ValueError) as exc:
            raise PlanValidationError(f"{label}_range_invalid") from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise PlanValidationError(f"{label}_range_invalid")
        parsed.append((start, end))
    return tuple(parsed)


def _dict_sequence(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PlanValidationError(f"{label}_must_be_object_list")
    return tuple(value)


def _parse_hook(value: object) -> HookPlan:
    if not isinstance(value, dict):
        raise PlanValidationError("hook_invalid")
    hook_id = value.get("id")
    rank = value.get("rank")
    if not isinstance(hook_id, str) or not hook_id.strip():
        raise PlanValidationError("hook_id_required")
    if not isinstance(rank, int):
        raise PlanValidationError("hook_rank_required")
    segments = _ranges(value.get("segments"), "hook_segments")
    if not segments:
        raise PlanValidationError("hook_segments_required")
    proof_assets = value.get("proof_assets", [])
    if not isinstance(proof_assets, list) or not all(isinstance(item, str) for item in proof_assets):
        raise PlanValidationError("hook_proof_assets_invalid")
    return HookPlan(hook_id.strip(), rank, segments, tuple(proof_assets))
