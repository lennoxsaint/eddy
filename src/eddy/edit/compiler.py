"""decisions -> EDL compiler. All mechanical invariants live here.

Pipeline:
1. remove intervals = decisions (retakes + cuts) + deterministic gap-tightening
2. clamp/merge -> complement = keep ranges
3. snap every keep edge to word boundaries with pads (never into a neighbor word)
4. drop debris ranges (< min_range_s), recompute duration

Model output that can't compile returns CompileError with a structured payload
the model can repair against.
"""

from __future__ import annotations

from pathlib import Path

from eddy.config import GatesConfig, RenderConfig
from eddy.edit.schema import EditDecisions, Edl, EdlRange

GAP_TIGHTEN_THRESHOLD_S = 0.68  # from approved shorts standard
GAP_LEAVE_HANDLE_S = 0.12  # silence left on each side of a tightened gap


class CompileError(ValueError):
    def __init__(self, problems: list[dict]):
        self.problems = problems
        super().__init__(f"{len(problems)} compile problem(s): {problems[:3]}")


def _clip_by_protected(intervals, protected_moments):
    """Drop the part of each remove-interval that would take the MAJORITY of a
    protected span. Smaller bites inside a protection are normal editing."""
    clipped: list[tuple[float, float]] = []
    for s, e in intervals:
        pieces = [(s, e)]
        for pm in protected_moments:
            span = max(0.1, pm.end_s - pm.start_s)
            next_pieces: list[tuple[float, float]] = []
            for ps, pe in pieces:
                overlap = min(pe, pm.end_s) - max(ps, pm.start_s)
                if overlap > 0 and overlap / span > 0.5:
                    if pm.start_s - ps > 0.2:
                        next_pieces.append((ps, pm.start_s))
                    if pe - pm.end_s > 0.2:
                        next_pieces.append((pm.end_s, pe))
                else:
                    next_pieces.append((ps, pe))
            pieces = next_pieces
        clipped.extend(pieces)
    return clipped


def silence_cut_intervals(
    silence_spans: list[dict], words: list[dict], min_cut_s: float, handle_s: float
) -> list[tuple[float, float]]:
    """Audio-truth silence removal: collapse every word-free silent span >= min_cut_s
    to a ~2*handle micro-pause. This is what kills 'mouth moving, no sound' — spans that
    produce no transcribed words and so are invisible to inter-word gap tightening."""
    out: list[tuple[float, float]] = []
    for sp in silence_spans:
        s, e = float(sp["start"]), float(sp["end"])
        if e - s < min_cut_s:
            continue
        rs, re_ = s + handle_s, e - handle_s
        if re_ - rs <= 0.05:
            continue
        # safety: never remove a region that overlaps a transcribed word
        if any(w["start"] < re_ and w["end"] > rs for w in words):
            continue
        out.append((rs, re_))
    return out


def _merge(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def gap_tighten_intervals(words: list[dict], threshold_s: float = GAP_TIGHTEN_THRESHOLD_S) -> list[tuple[float, float]]:
    """Cut the CENTER of long inter-word gaps, leaving handles both sides."""
    out = []
    for prev, nxt in zip(words, words[1:]):
        gap = nxt["start"] - prev["end"]
        if gap >= threshold_s:
            s = prev["end"] + GAP_LEAVE_HANDLE_S
            e = nxt["start"] - GAP_LEAVE_HANDLE_S
            if e - s > 0.05:
                out.append((s, e))
    return out


def compile_edl(
    decisions: EditDecisions,
    words: list[dict],
    source_path: str,
    duration_s: float,
    render_cfg: RenderConfig,
    gates_cfg: GatesConfig,
    tighten_gaps: bool = True,
    silence_spans: list[dict] | None = None,
) -> Edl:
    problems: list[dict] = []

    removes: list[tuple[float, float]] = []
    for start, end, label in decisions.all_remove_intervals():
        if end <= start:
            problems.append({"type": "inverted_interval", "start_s": start, "end_s": end, "label": label})
            continue
        if start < 0 or end > duration_s + 1.0:
            problems.append({"type": "out_of_bounds", "start_s": start, "end_s": end, "duration_s": duration_s})
            continue
        removes.append((max(0.0, start), min(duration_s, end)))

    if problems:
        raise CompileError(problems)

    # Protected moments win deterministically — but protection means "this content
    # survives", not "nothing inside may be touched". Models routinely protect whole
    # beats wall-to-wall; a cut is only voided when it would remove the MAJORITY of
    # the protected span. Smaller bites inside a protection are normal editing.
    removes = _clip_by_protected(removes, decisions.protected_moments)

    # Audio-truth silence removal: collapse word-free silent spans (false starts,
    # swallowed words, pre-speech lip movement) that inter-word gap tightening misses.
    # Protected beats keep their deliberate silence.
    if silence_spans:
        sil = silence_cut_intervals(
            silence_spans, words, gates_cfg.silence_min_cut_s, gates_cfg.silence_handle_s
        )
        removes += _clip_by_protected(sil, decisions.protected_moments)

    if tighten_gaps:
        removes += gap_tighten_intervals(words)
    removes = _merge(removes)

    # complement -> keep ranges
    keeps: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in removes:
        if s > cursor:
            keeps.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration_s:
        keeps.append((cursor, duration_s))

    pad_before = render_cfg.cut_pad_before_ms / 1000
    pad_after = render_cfg.cut_pad_after_ms / 1000

    ranges: list[EdlRange] = []
    for s, e in keeps:
        snapped = _snap_to_words(s, e, words, pad_before, pad_after, duration_s)
        if snapped is None:
            continue  # no words inside: silence debris between cuts
        ns, ne, sh, eh = snapped
        if ne - ns < gates_cfg.min_range_s:
            continue
        ranges.append(
            EdlRange(start=round(ns, 3), end=round(ne, 3), start_handle_s=round(sh, 3), end_handle_s=round(eh, 3))
        )

    if not ranges:
        raise CompileError([{"type": "empty_edit", "detail": "no keep ranges survived compilation"}])

    # annotate beats from decisions metadata
    for r in ranges:
        for beat in decisions.x_eddy.beats:
            if beat.get("start_s", 0) <= r.start < beat.get("end_s", 0):
                r.beat = beat.get("label", "")
                break

    merged: list[EdlRange] = []
    for r in ranges:
        if merged and r.start <= merged[-1].end:
            merged[-1].end = max(merged[-1].end, r.end)
            merged[-1].end_handle_s = r.end_handle_s
        else:
            merged.append(r)

    total = sum(r.end - r.start for r in merged)
    return Edl(
        sources={"camera": source_path},
        ranges=merged,
        total_duration_s=round(total, 2),
    )


def _snap_to_words(
    s: float,
    e: float,
    words: list[dict],
    pad_before: float,
    pad_after: float,
    duration_s: float,
) -> tuple[float, float, float, float] | None:
    """Snap [s,e] so it starts pad_before ahead of the first word fully inside and
    ends pad_after past the last word fully inside. Pads never reach a neighbor word.
    Returns (start, end, start_handle, end_handle) or None when no word is inside."""
    inside = [w for w in words if w["start"] >= s - 0.02 and w["end"] <= e + 0.02]
    if not inside:
        return None
    first, last = inside[0], inside[-1]
    idx_first = words.index(first)
    idx_last = words.index(last)
    prev_end = words[idx_first - 1]["end"] if idx_first > 0 else 0.0
    next_start = words[idx_last + 1]["start"] if idx_last + 1 < len(words) else duration_s

    start = max(first["start"] - pad_before, prev_end, 0.0)
    end = min(last["end"] + pad_after, next_start, duration_s)
    return start, end, first["start"] - start, end - last["end"]


def cut_transcript(edl: Edl, phrases: list[dict]) -> list[dict]:
    """Phrases surviving the edit, with output-timeline timestamps."""
    out = []
    cursor = 0.0
    for r in edl.ranges:
        for p in phrases:
            mid = (p["start"] + p["end"]) / 2
            if r.start <= mid <= r.end:
                out.append(
                    {
                        **p,
                        "out_start": round(cursor + p["start"] - r.start, 2),
                        "out_end": round(cursor + p["end"] - r.start, 2),
                    }
                )
        cursor += r.end - r.start
    return out


def write_benchmark(edl: Edl, run_dir: Path, slug: str) -> Path:
    import json

    path = Path(run_dir) / "final" / "edit-decisions.benchmark.json"
    path.write_text(json.dumps(edl.to_benchmark_format(slug=slug), indent=2))
    return path
