"""`eddy bundle` — a redacted diagnostic archive for bug reports.

Includes the audit trail (manifest hashes, state, receipts, per-iteration JSON) + an environment
fingerprint, with PII stripped: transcript-derived text (quotes/summaries/titles/descriptions) is
redacted and home-dir paths are scrubbed. Raw footage, the transcript, and face frames are never
included.
"""

from __future__ import annotations

import json
import platform
import shutil
import tempfile
from pathlib import Path

from eddy.privacy import redact_paths

# keys whose string values carry transcript-derived content (PII)
_REDACT_KEYS = {
    "quote", "text", "summary", "reason", "hook", "title", "description",
    "before_text", "after_text", "removed_summary", "prompt", "fix_note", "label", "error",
}


def _scrub(s: str) -> str:
    # absolute-path scrub lives in eddy.privacy now (shared with the CLI-subprocess provider)
    return redact_paths(s)


def _redact(obj):
    if isinstance(obj, dict):
        return {k: ("[redacted]" if (k in _REDACT_KEYS and isinstance(v, str)) else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    if isinstance(obj, str):
        return _scrub(obj)
    return obj


def _redact_json_to(src: Path, dst: Path) -> None:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(_redact(json.loads(src.read_text())), indent=1))
    except Exception:
        pass  # skip unreadable/non-JSON


def build_bundle(run_dir: Path, out_path: Path | None = None) -> Path:
    import eddy

    run_dir = Path(run_dir)
    out_path = Path(out_path) if out_path else run_dir / "eddy-bundle.zip"
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "bundle"
        stage.mkdir()
        (stage / "environment.json").write_text(json.dumps({
            "eddy_version": eddy.__version__,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "ffprobe": bool(shutil.which("ffprobe")),
        }, indent=1))
        for name in ("manifest.json", "state.json"):
            if (run_dir / name).exists():
                _redact_json_to(run_dir / name, stage / name)
        if (run_dir / "receipts.jsonl").exists():
            lines = []
            for ln in (run_dir / "receipts.jsonl").read_text().splitlines():
                try:
                    lines.append(json.dumps(_redact(json.loads(ln))))
                except Exception:
                    continue
            (stage / "receipts.jsonl").write_text("\n".join(lines) + "\n")
        for j in run_dir.glob("iterations/**/*.json"):
            _redact_json_to(j, stage / j.relative_to(run_dir))
        shutil.make_archive(str(out_path.with_suffix("")), "zip", stage)
    return out_path
