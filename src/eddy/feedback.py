"""Typed owner feedback captured beside a run before it becomes product doctrine."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


ISSUE_CATEGORIES = {"run_specific", "deterministic_bug", "quality_preference", "doctrine"}
ISSUE_SCOPES = {"current_run", "future_edits"}
VERDICTS = {"approved", "approved_after_repair", "changes_requested"}
PROMOTION_CLASSES = {"project_specific", "owner_profile", "generic_candidate"}
PROJECT_FACT_FIELDS = {
    "person_or_spelling",
    "url",
    "offer_or_price",
    "currency",
    "cta",
    "logo_or_brand_asset",
    "runtime_target",
    "speaker_palette",
    "one_off_visual_choice",
}


def record_owner_feedback(run_dir: Path, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    schema = payload.get("schema_version")
    if schema not in {"owner-feedback-v1", "owner-verdict-v2"}:
        raise ValueError("owner_feedback_schema_invalid")
    if payload.get("job_id") != job_id:
        raise ValueError("owner_feedback_job_id_mismatch")
    verdict = payload.get("verdict")
    if verdict not in VERDICTS:
        raise ValueError("owner_feedback_verdict_invalid")
    approval_scope = payload.get("approval_scope")
    if not isinstance(approval_scope, list) or not approval_scope or not all(
        isinstance(item, str) and item.strip() for item in approval_scope
    ):
        raise ValueError("owner_feedback_approval_scope_invalid")
    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("owner_feedback_issues_invalid")
    normalized_issues = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("owner_feedback_issue_invalid")
        category = issue.get("category")
        scope = issue.get("scope")
        if category not in ISSUE_CATEGORIES:
            raise ValueError("owner_feedback_issue_category_invalid")
        if scope not in ISSUE_SCOPES:
            raise ValueError("owner_feedback_issue_scope_invalid")
        if not all(
            isinstance(issue.get(field), str) and str(issue[field]).strip()
            for field in ("artifact", "evidence", "desired_correction")
        ):
            raise ValueError("owner_feedback_issue_detail_required")
        normalized_issues.append(
            {
                "artifact": issue["artifact"],
                "evidence": issue["evidence"],
                "category": category,
                "scope": scope,
                "desired_correction": issue["desired_correction"],
                **_promotion_fields(issue, schema=str(schema)),
            }
        )
    normalized = {
        "schema_version": schema,
        "job_id": job_id,
        "verdict": verdict,
        "approval_scope": approval_scope,
        "summary": str(payload.get("summary", "")).strip(),
        "issues": normalized_issues,
    }
    output = run_dir / "review" / (
        "owner-verdict.json" if schema == "owner-verdict-v2" else "owner-feedback.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    if schema == "owner-verdict-v2":
        _write_correction_candidates(run_dir, normalized_issues)
    return {"status": "recorded", "path": str(output), "feedback": normalized}


def _promotion_fields(issue: dict[str, Any], *, schema: str) -> dict[str, Any]:
    if schema == "owner-feedback-v1":
        return {}
    generalized = issue.get("generalized_rule")
    eval_id = issue.get("eval_id")
    classification = issue.get("promotion_class")
    source_ref = issue.get("source_ref")
    project_fact_fields = issue.get("project_fact_fields")
    if not isinstance(generalized, str) or not generalized.strip():
        raise ValueError("owner_feedback_generalized_rule_required")
    if not isinstance(eval_id, str) or not eval_id.strip():
        raise ValueError("owner_feedback_eval_id_required")
    if classification not in PROMOTION_CLASSES:
        raise ValueError("owner_feedback_promotion_class_invalid")
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError("owner_feedback_source_ref_required")
    if not isinstance(project_fact_fields, list) or not all(
        isinstance(item, str) and item in PROJECT_FACT_FIELDS
        for item in project_fact_fields
    ):
        raise ValueError("owner_feedback_project_fact_fields_invalid")
    if classification != "project_specific" and (
        project_fact_fields or _contains_literal_project_fact(generalized)
    ):
        raise ValueError("owner_feedback_project_fact_cannot_promote")
    return {
        "generalized_rule": generalized.strip(),
        "eval_id": eval_id.strip(),
        "promotion_class": classification,
        "source_ref": source_ref.strip(),
        "project_fact_fields": list(dict.fromkeys(project_fact_fields)),
    }


def _write_correction_candidates(
    run_dir: Path,
    issues: list[dict[str, Any]],
) -> None:
    candidates = [
        {
            "schema_version": "eddy-correction-candidate-v1",
            "eval_id": issue["eval_id"],
            "generalized_rule": issue["generalized_rule"],
            "promotion_class": issue["promotion_class"],
            "source_ref": issue["source_ref"],
            "project_fact_fields": issue["project_fact_fields"],
            "current_run_status": "apply_now",
            "owner_profile_status": (
                "eligible_after_eval"
                if issue["promotion_class"] == "owner_profile"
                else "not_applicable"
            ),
            "generic_core_status": (
                "requires_cross_project_recurrence_or_explicit_owner_designation"
                if issue["promotion_class"] == "generic_candidate"
                else "not_applicable"
            ),
        }
        for issue in issues
    ]
    output = run_dir / "review" / "correction-candidates.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": "eddy-correction-candidates-v1",
                "candidates": candidates,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    os.replace(temporary, output)


def _contains_literal_project_fact(rule: str) -> bool:
    """Catch concrete URLs and offer amounts without rejecting rules about their class."""

    return bool(
        re.search(r"https?://|www\.", rule, flags=re.IGNORECASE)
        or re.search(
            r"(?:[$£€¥]\s?\d|\b(?:aud|usd|gbp|eur)\s?\d|\b\d[\d,]*\s?(?:dollars?|pounds?|euros?)\b)",
            rule,
            flags=re.IGNORECASE,
        )
    )
