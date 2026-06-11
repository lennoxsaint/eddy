#!/usr/bin/env python3
"""Diff Eddy's cut against the prior pipeline's edit on the same video.

Usage: benchmark_diff.py <eddy_benchmark.json> <prior_edit-decisions.json>
Reports kept-range overlap, durations, and divergent regions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_ranges(path: Path) -> list[tuple[float, float]]:
    data = json.loads(path.read_text())
    return sorted((float(r["start"]), float(r["end"])) for r in data["ranges"])


def total(ranges: list[tuple[float, float]]) -> float:
    return sum(e - s for s, e in ranges)


def intersect(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    out, i, j = 0.0, 0, 0
    while i < len(a) and j < len(b):
        s = max(a[i][0], b[j][0])
        e = min(a[i][1], b[j][1])
        if e > s:
            out += e - s
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def divergences(a: list[tuple[float, float]], b: list[tuple[float, float]], min_s: float = 5.0) -> list[dict]:
    """Regions kept by one but not the other, larger than min_s."""
    out = []
    for s, e in a:
        cursor = s
        for bs, be in b:
            if be <= cursor or bs >= e:
                continue
            if bs > cursor and bs - cursor >= min_s:
                out.append({"start": round(cursor, 1), "end": round(bs, 1), "s": round(bs - cursor, 1)})
            cursor = max(cursor, be)
        if e - cursor >= min_s:
            out.append({"start": round(cursor, 1), "end": round(e, 1), "s": round(e - cursor, 1)})
    return out


def main() -> None:
    eddy_path, prior_path = Path(sys.argv[1]), Path(sys.argv[2])
    eddy, prior = load_ranges(eddy_path), load_ranges(prior_path)
    inter = intersect(eddy, prior)
    report = {
        "eddy": {"ranges": len(eddy), "kept_s": round(total(eddy), 1)},
        "prior": {"ranges": len(prior), "kept_s": round(total(prior), 1)},
        "overlap_s": round(inter, 1),
        "overlap_pct_of_eddy": round(100 * inter / total(eddy), 1) if eddy else 0,
        "overlap_pct_of_prior": round(100 * inter / total(prior), 1) if prior else 0,
        "kept_by_eddy_not_prior": divergences(eddy, prior),
        "kept_by_prior_not_eddy": divergences(prior, eddy),
    }
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
