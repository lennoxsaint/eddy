"""Validated host-authored edit plans for the thin Eddy runtime."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .proof import screen_proof_share


class PlanValidationError(ValueError):
    """The host plan violates the public Eddy v3 contract."""


@dataclass(frozen=True, slots=True)
class BodyPlan:
    keep: tuple[tuple[float, float], ...]
    drop: tuple[tuple[float, float], ...]
    retake_groups: tuple["RetakeGroup", ...]


@dataclass(frozen=True, slots=True)
class RetakeVariant:
    id: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class RetakeGroup:
    id: str
    selected_variant_id: str
    variants: tuple[RetakeVariant, ...]


@dataclass(frozen=True, slots=True)
class EditorialResolution:
    candidate_id: str
    action: str
    selected_variant_id: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class EditorialReview:
    coverage: tuple[tuple[float, float], ...]
    resolutions: tuple[EditorialResolution, ...]


@dataclass(frozen=True, slots=True)
class ShortPlan:
    id: str
    segments: tuple[tuple[float, float], ...]
    drop: tuple[tuple[float, float], ...]
    screen_proof_segments: tuple[tuple[float, float], ...]
    motion_beats: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class HookPlan:
    id: str
    rank: int
    segments: tuple[tuple[float, float], ...]
    proof_assets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrivacyMask:
    id: str
    hook_ids: tuple[str, ...]
    start: float
    end: float
    x: int
    y: int
    width: int
    height: int
    color: str


@dataclass(frozen=True, slots=True)
class EditPlanV3:
    schema_version: str
    source_hashes: dict[str, str]
    protected: tuple[dict[str, Any], ...]
    editorial_review: EditorialReview
    body: BodyPlan
    hooks: tuple[HookPlan, HookPlan, HookPlan]
    privacy_masks: tuple[PrivacyMask, ...]
    shorts: tuple[ShortPlan, ...]
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
            "editorial_review",
            "body",
            "hooks",
            "privacy_masks",
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
        privacy_masks = _parse_privacy_masks(
            payload.get("privacy_masks", []),
            valid_hook_ids={hook.id for hook in hooks},
        )

        raw_review = payload.get("editorial_review")
        if not isinstance(raw_review, dict):
            raise PlanValidationError("editorial_review_required")
        editorial_review = EditorialReview(
            coverage=_ranges(raw_review.get("coverage"), "editorial_coverage"),
            resolutions=_parse_resolutions(raw_review.get("resolutions")),
        )

        raw_body = payload.get("body")
        if not isinstance(raw_body, dict):
            raise PlanValidationError("shared_body_required")
        body = BodyPlan(
            keep=_ranges(raw_body.get("keep"), "body_keep"),
            drop=_ranges(raw_body.get("drop", []), "body_drop"),
            retake_groups=_parse_retake_groups(raw_body.get("retake_groups", [])),
        )
        if not body.keep:
            raise PlanValidationError("shared_body_keep_required")

        hashes = payload.get("source_hashes")
        if not isinstance(hashes, dict) or not hashes:
            raise PlanValidationError("source_hashes_required")
        if not all(isinstance(key, str) and _valid_hash(value) for key, value in hashes.items()):
            raise PlanValidationError("source_hash_invalid")

        raw_shorts = payload.get("shorts", [])
        if not isinstance(raw_shorts, list) or not 3 <= len(raw_shorts) <= 5:
            raise PlanValidationError("shorts_count_must_be_3_to_5")
        dual_source = any(
            "screen" in name.lower() or "display" in name.lower() for name in hashes
        )
        shorts = tuple(_parse_short(item, dual_source=dual_source) for item in raw_shorts)
        short_ids = [item.id for item in shorts]
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
            protected_range = (start, end)
            if not _range_fully_covered(protected_range, body.keep):
                raise PlanValidationError("protected_span_missing_from_shared_body")
            if any(_overlaps(protected_range, dropped) for dropped in body.drop):
                raise PlanValidationError("body_drop_overlaps_protected_span")
            for group in body.retake_groups:
                for variant in group.variants:
                    variant_range = (variant.start, variant.end)
                    if (
                        variant.id != group.selected_variant_id
                        and _overlaps(protected_range, variant_range)
                    ):
                        raise PlanValidationError("retake_drop_overlaps_protected_span")
            for short in shorts:
                if any(_overlaps(protected_range, dropped) for dropped in short.drop):
                    raise PlanValidationError("short_drop_overlaps_protected_span")

        motion_beats = _dict_sequence(payload.get("motion_beats", []), "motion_beats")
        _validate_motion_beats(motion_beats, label="long_motion")
        for hook in hooks:
            applicable = tuple(
                beat
                for beat in motion_beats
                if beat.get("hook_id") in {None, "*", hook.id}
            )
            if len(applicable) < 2:
                raise PlanValidationError(f"long_two_motion_beats_required:{hook.id}")
            if min(float(beat["start"]) for beat in applicable) > 2.0:
                raise PlanValidationError(f"long_hook_motion_must_start_by_two_seconds:{hook.id}")

        return cls(
            schema_version="edit-plan-v3",
            source_hashes=dict(hashes),
            protected=protected,
            editorial_review=editorial_review,
            body=body,
            hooks=hooks,  # type: ignore[arg-type]
            privacy_masks=privacy_masks,
            shorts=tuple(shorts),
            motion_beats=motion_beats,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_hashes": self.source_hashes,
            "protected": list(self.protected),
            "editorial_review": {
                "coverage": [list(item) for item in self.editorial_review.coverage],
                "resolutions": [
                    {
                        "candidate_id": item.candidate_id,
                        "action": item.action,
                        "selected_variant_id": item.selected_variant_id,
                        "reason": item.reason,
                    }
                    for item in self.editorial_review.resolutions
                ],
            },
            "body": {
                "keep": [list(item) for item in self.body.keep],
                "drop": [list(item) for item in self.body.drop],
                "retake_groups": [
                    {
                        "id": group.id,
                        "selected_variant_id": group.selected_variant_id,
                        "variants": [
                            {"id": variant.id, "start": variant.start, "end": variant.end}
                            for variant in group.variants
                        ],
                    }
                    for group in self.body.retake_groups
                ],
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
            "privacy_masks": [
                {
                    "id": mask.id,
                    "hook_ids": list(mask.hook_ids),
                    "start": mask.start,
                    "end": mask.end,
                    "x": mask.x,
                    "y": mask.y,
                    "width": mask.width,
                    "height": mask.height,
                    "color": mask.color,
                }
                for mask in self.privacy_masks
            ],
            "shorts": [
                {
                    "id": item.id,
                    "segments": [list(value) for value in item.segments],
                    "drop": [list(value) for value in item.drop],
                    "screen_proof_segments": [list(value) for value in item.screen_proof_segments],
                    "motion_beats": list(item.motion_beats),
                }
                for item in self.shorts
            ],
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


def _parse_privacy_masks(
    value: object,
    *,
    valid_hook_ids: set[str],
) -> tuple[PrivacyMask, ...]:
    rows = _dict_sequence(value, "privacy_masks")
    masks: list[PrivacyMask] = []
    seen_ids: set[str] = set()
    for row in rows:
        mask_id = row.get("id")
        hook_ids = row.get("hook_ids")
        if not isinstance(mask_id, str) or not mask_id.strip():
            raise PlanValidationError("privacy_mask_id_required")
        mask_id = mask_id.strip()
        if mask_id in seen_ids:
            raise PlanValidationError("privacy_mask_ids_must_be_unique")
        seen_ids.add(mask_id)
        if (
            not isinstance(hook_ids, list)
            or not hook_ids
            or not all(isinstance(hook_id, str) and hook_id.strip() for hook_id in hook_ids)
        ):
            raise PlanValidationError("privacy_mask_hook_ids_required")
        normalized_hook_ids = tuple(hook_id.strip() for hook_id in hook_ids)
        if any(hook_id not in valid_hook_ids for hook_id in normalized_hook_ids):
            raise PlanValidationError("privacy_mask_hook_unknown")
        try:
            start = float(row["start"])
            end = float(row["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PlanValidationError("privacy_mask_range_invalid") from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise PlanValidationError("privacy_mask_range_invalid")
        coordinates = (row.get("x"), row.get("y"), row.get("width"), row.get("height"))
        if not all(isinstance(item, int) and not isinstance(item, bool) for item in coordinates):
            raise PlanValidationError("privacy_mask_rectangle_invalid")
        x, y, width, height = coordinates
        assert isinstance(x, int) and isinstance(y, int)
        assert isinstance(width, int) and isinstance(height, int)
        if x < 0 or y < 0 or width <= 0 or height <= 0:
            raise PlanValidationError("privacy_mask_rectangle_invalid")
        if x + width > 1920 or y + height > 1080:
            raise PlanValidationError("privacy_mask_rectangle_out_of_bounds")
        color = row.get("color", "0x111827")
        if (
            not isinstance(color, str)
            or len(color) != 8
            or not color.startswith("0x")
            or any(character not in "0123456789abcdefABCDEF" for character in color[2:])
        ):
            raise PlanValidationError("privacy_mask_color_invalid")
        masks.append(
            PrivacyMask(
                id=mask_id,
                hook_ids=normalized_hook_ids,
                start=start,
                end=end,
                x=x,
                y=y,
                width=width,
                height=height,
                color=color,
            )
        )
    return tuple(masks)


def _parse_resolutions(value: object) -> tuple[EditorialResolution, ...]:
    if not isinstance(value, list):
        raise PlanValidationError("editorial_resolutions_required")
    allowed_actions = {"keep_last", "keep_variant", "drop_all", "intentional_repeat", "tighten_gap"}
    parsed: list[EditorialResolution] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("candidate_id"), str):
            raise PlanValidationError("editorial_resolution_invalid")
        action = item.get("action")
        if action not in allowed_actions:
            raise PlanValidationError("editorial_resolution_action_invalid")
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise PlanValidationError("editorial_resolution_reason_required")
        selected = item.get("selected_variant_id")
        if selected is not None and not isinstance(selected, str):
            raise PlanValidationError("editorial_selected_variant_invalid")
        parsed.append(EditorialResolution(item["candidate_id"], action, selected, reason.strip()))
    if len({item.candidate_id for item in parsed}) != len(parsed):
        raise PlanValidationError("editorial_resolution_ids_must_be_unique")
    return tuple(parsed)


def _parse_retake_groups(value: object) -> tuple[RetakeGroup, ...]:
    if not isinstance(value, list):
        raise PlanValidationError("retake_groups_must_be_object_list")
    groups: list[RetakeGroup] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise PlanValidationError("retake_group_invalid")
        selected = item.get("selected_variant_id")
        variants_raw = item.get("variants")
        if not isinstance(selected, str) or not isinstance(variants_raw, list) or len(variants_raw) < 2:
            raise PlanValidationError("retake_group_variants_invalid")
        variants: list[RetakeVariant] = []
        for variant in variants_raw:
            if not isinstance(variant, dict) or not isinstance(variant.get("id"), str):
                raise PlanValidationError("retake_variant_invalid")
            ranges = _ranges([[variant.get("start"), variant.get("end")]], "retake_variant")
            variants.append(RetakeVariant(variant["id"], ranges[0][0], ranges[0][1]))
        if selected not in {variant.id for variant in variants}:
            raise PlanValidationError("retake_selected_variant_unknown")
        groups.append(RetakeGroup(item["id"], selected, tuple(variants)))
    return tuple(groups)


def _parse_short(value: object, *, dual_source: bool) -> ShortPlan:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"].strip():
        raise PlanValidationError("short_candidate_invalid")
    segments = _ranges(value.get("segments"), "short_segments")
    drops = _ranges(value.get("drop", []), "short_drop")
    if any(not _range_fully_covered(dropped, segments) for dropped in drops):
        raise PlanValidationError("short_drop_outside_segments")
    effective_segments = _subtract_ranges(segments, drops)
    if not effective_segments:
        raise PlanValidationError("short_drop_removes_entire_candidate")
    proof = _ranges(value.get("screen_proof_segments", []), "short_screen_proof")
    beats = _dict_sequence(value.get("motion_beats", []), "short_motion_beats")
    if len(beats) < 2:
        raise PlanValidationError("short_two_motion_beats_required")
    _validate_motion_beats(beats, label="short_motion")
    if min(float(beat["start"]) for beat in beats) > 2.0:
        raise PlanValidationError("short_hook_motion_must_start_by_two_seconds")
    effective_proof = _subtract_ranges(proof, drops)
    if dual_source and screen_proof_share(effective_proof, effective_segments) < 0.25:
        raise PlanValidationError("short_screen_proof_below_25_percent")
    return ShortPlan(value["id"].strip(), segments, drops, proof, beats)


def _validate_motion_beats(beats: tuple[dict[str, Any], ...], *, label: str) -> None:
    ids: list[str] = []
    for beat in beats:
        try:
            start, duration = float(beat["start"]), float(beat["dur"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PlanValidationError(f"{label}_beat_invalid") from exc
        beat_id = beat.get("id")
        layout = beat.get("layout")
        if (
            start < 0
            or duration <= 0
            or not isinstance(beat_id, str)
            or not beat_id.strip()
            or not isinstance(layout, str)
            or not layout.strip()
        ):
            raise PlanValidationError(f"{label}_beat_invalid")
        ids.append(beat_id)
    if len(set(ids)) != len(ids):
        raise PlanValidationError(f"{label}_beat_ids_must_be_unique")


def _overlaps(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _range_fully_covered(
    target: tuple[float, float],
    ranges: tuple[tuple[float, float], ...],
) -> bool:
    cursor = target[0]
    for start, end in sorted(ranges):
        if end <= cursor:
            continue
        if start > cursor + 0.001:
            return False
        cursor = max(cursor, end)
        if cursor >= target[1] - 0.001:
            return True
    return False


def _subtract_ranges(
    ranges: tuple[tuple[float, float], ...],
    drops: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    remaining: list[tuple[float, float]] = []
    for range_start, range_end in ranges:
        pieces = [(range_start, range_end)]
        for drop_start, drop_end in drops:
            next_pieces: list[tuple[float, float]] = []
            for piece_start, piece_end in pieces:
                if drop_end <= piece_start or drop_start >= piece_end:
                    next_pieces.append((piece_start, piece_end))
                    continue
                if piece_start < drop_start:
                    next_pieces.append((piece_start, min(piece_end, drop_start)))
                if drop_end < piece_end:
                    next_pieces.append((max(piece_start, drop_end), piece_end))
            pieces = next_pieces
        remaining.extend(piece for piece in pieces if piece[1] - piece[0] > 0.001)
    return tuple(remaining)
