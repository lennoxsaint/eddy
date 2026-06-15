"""Creator-facing review notes for the launch kit.

Eddy often ships a best-attempt cut (the q4 judge plateaus, dense sources floor over the ceiling).
A non-engineer can't read judge.json / receipts. This turns the judge's defects + the length/QA
status into a plain-language 'review these moments before publishing' note.
"""

from __future__ import annotations

import json
from pathlib import Path


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def format_review(defects: list[dict], duration_s: float, ceiling_s: float,
                  qa_pass: bool, shipped_with_failures: bool) -> str:
    lines = ["# Review before publishing", ""]
    lines.append(
        "This is Eddy's strongest attempt — it didn't fully pass every check, so skim the flagged moments below."
        if shipped_with_failures
        else "Eddy shipped a clean first cut. A quick skim is still worth it:"
    )
    lines.append("")

    flagged = [d for d in defects if d.get("severity") == "major"] + [d for d in defects if d.get("severity") != "major"]
    if flagged:
        lines.append(f"## {len(flagged)} moment(s) Eddy was unsure about")
        for d in flagged[:15]:
            typ = str(d.get("type", "issue")).replace("_", " ")
            quote = (d.get("quote") or "").strip()
            lines.append(f"- **[{_ts(d.get('out_s', 0))}]** {typ}" + (f' — "{quote[:80]}"' if quote else ""))
        lines.append("")

    if duration_s > ceiling_s + 5:
        lines.append(f"## Length: {_ts(duration_s)} (target {_ts(ceiling_s)})")
        lines.append(
            f"A long-form edit — {_ts(duration_s - ceiling_s)} over the target ceiling. Expected for a "
            "dense source; this is not a short. Trim further by hand if you want it tighter."
        )
        lines.append("")

    lines.append(f"**Final QA:** {'PASS' if qa_pass else 'CHECK `final/qa-final.json`'}")
    return "\n".join(lines) + "\n"


def build_review(run_dir: Path, iter_dir: Path, duration_s: float, ceiling_s: float) -> dict:
    """Read the chosen iteration's judge + final QA and render review notes into final/REVIEW.md."""
    run_dir = Path(run_dir)
    defects: list[dict] = []
    judge_path = iter_dir / "judge.json"
    if judge_path.exists():
        try:
            defects = json.loads(judge_path.read_text()).get("defects", []) or []
        except Exception:
            defects = []
    qa_pass = False
    qa_path = run_dir / "final" / "qa-final.json"
    if qa_path.exists():
        try:
            qa_pass = bool(json.loads(qa_path.read_text()).get("pass"))
        except Exception:
            qa_pass = False
    shipped_with_failures = (not qa_pass) or bool(defects)
    md = format_review(defects, duration_s, ceiling_s, qa_pass, shipped_with_failures)
    (run_dir / "final" / "REVIEW.md").write_text(md)
    return {"flagged": len(defects), "shipped_with_failures": shipped_with_failures, "qa_pass": qa_pass}
