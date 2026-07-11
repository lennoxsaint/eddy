"""Typed owner feedback captured beside a run before it becomes product doctrine."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ISSUE_CATEGORIES = {"run_specific", "deterministic_bug", "quality_preference", "doctrine"}
ISSUE_SCOPES = {"current_run", "future_edits"}
VERDICTS = {"approved", "approved_after_repair", "changes_requested"}


def record_owner_feedback(run_dir: Path, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "owner-feedback-v1":
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
            }
        )
    normalized = {
        "schema_version": "owner-feedback-v1",
        "job_id": job_id,
        "verdict": verdict,
        "approval_scope": approval_scope,
        "summary": str(payload.get("summary", "")).strip(),
        "issues": normalized_issues,
    }
    output = run_dir / "review" / "owner-feedback.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    return {"status": "recorded", "path": str(output), "feedback": normalized}
