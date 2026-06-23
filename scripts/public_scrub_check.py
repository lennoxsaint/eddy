#!/usr/bin/env python3
"""Public-release scrub for Eddy.

The check is intentionally conservative around credentials and intentionally explicit around
personal/local path leftovers. It scans tracked files only, so ignored run media, caches, and local
keys do not block a public repo release unless they are accidentally tracked.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = {
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "descript_token": re.compile(r"\bdx_(?:bearer|secret)_[A-Za-z0-9-]{20,}\b"),
    "private_key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
}

LOCAL_PATH_PATTERNS = {
    "absolute_lennox_path": re.compile(r"/Users/lennoxsaint"),
    "absolute_yassy_path": re.compile(r"/Users/yassybabes"),
}

ALLOWLIST_LOCAL_PATH_FILES = {
    "docs/research-notes.md",
    "docs/decision-log.md",
}


def tracked_files() -> list[Path]:
    out = subprocess.check_output(["git", "-C", str(ROOT), "ls-files"], text=True)
    return [ROOT / line for line in out.splitlines() if line.strip()]


def scan_file(path: Path) -> list[dict[str, str | int]]:
    rel = path.relative_to(ROOT).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    findings: list[dict[str, str | int]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for name, pat in SECRET_PATTERNS.items():
            if pat.search(line):
                findings.append({"severity": "blocker", "type": name, "file": rel, "line": line_no})
        for name, pat in LOCAL_PATH_PATTERNS.items():
            if pat.search(line) and rel not in ALLOWLIST_LOCAL_PATH_FILES and not rel.startswith("vendor/"):
                findings.append({"severity": "blocker", "type": name, "file": rel, "line": line_no})
    return findings


def main() -> int:
    findings: list[dict[str, str | int]] = []
    for path in tracked_files():
        findings.extend(scan_file(path))
    report = {
        "status": "pass" if not findings else "fail",
        "tracked_files_scanned": len(tracked_files()),
        "findings": findings,
    }
    print(json.dumps(report, indent=2))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
