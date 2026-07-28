"""Atomic review-submission artifacts for the host-driven proof loop."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


REVIEW_FILES = {
    "review_passes": "review-passes.json",
    "production_score": "production-score.json",
    "professional_gates": "professional-gates.json",
    "verifier_review": "verifier-review.json",
    "open_items": "open-items.json",
}


def write_review_submission(attempt: Path, payload: dict[str, Any]) -> dict[str, str]:
    if payload.get("schema_version") != "eddy-review-submission-v1":
        raise ValueError("review_submission_schema_invalid")
    extra = sorted(set(payload) - {"schema_version", *REVIEW_FILES})
    if extra:
        raise ValueError(f"review_submission_fields_invalid:{','.join(extra)}")
    written: dict[str, str] = {}
    for key, filename in REVIEW_FILES.items():
        value = payload.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"review_submission_{key}_required")
        path = attempt / filename
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
        written[key] = str(path)
    return written
