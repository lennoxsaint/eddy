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

import math
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
    extra_protected: list | None = None,
    phrases: list[dict] | None = None,
    extract: bool = False,
) -> Edl:
    problems: list[dict] = []
    protected = list(decisions.protected_moments) + list(extra_protected or [])

    removes: list[tuple[float, float]] = []
    small_cut_bridges: list[tuple[float, float]] = []  # v1.6.3 extract bridge candidates
    for start, end, label in decisions.all_remove_intervals():
        if not (math.isfinite(start) and math.isfinite(end)):
            # NaN/inf survives every comparison below (all NaN comparisons are False) and would
            # become a real cut via max(0.0, nan)=0.0. Route it to the repair loop instead.
            problems.append({"type": "non_finite_interval", "start_s": start, "end_s": end, "label": label})
            continue
        if end <= start:
            problems.append({"type": "inverted_interval", "start_s": start, "end_s": end, "label": label})
            continue
        if start < 0 or end > duration_s + 1.0:
            problems.append({"type": "out_of_bounds", "start_s": start, "end_s": end, "duration_s": duration_s})
            continue
        s, e = max(0.0, start), min(duration_s, end)
        removes.append((s, e))
        # an extract's small CUT spans are the gaps that chop one explanation into slivers; bridge
        # them (drop the cut) so the on-topic keeps join. Retakes (duplicate takes) are never bridged.
        if label != "retake" and e - s <= gates_cfg.extract_bridge_gap_s:
            small_cut_bridges.append((s, e))

    if problems:
        raise CompileError(problems)

    # v1.6.3 bridge-then-retighten: re-admit the small off-topic cut gaps so the extract reads as a
    # few contiguous blocks instead of many slivers — but do it HERE, before silence removal, so the
    # silence inside a re-admitted bridge is still cut below (a post-inversion range merge replayed
    # that silence and failed the dead-air gate). Net: fewer blocks, clean audio. Extract only.
    if extract and small_cut_bridges:
        drop = set(small_cut_bridges)
        removes = [iv for iv in removes if iv not in drop]

    # Protected moments win deterministically — but protection means "this content
    # survives", not "nothing inside may be touched". Models routinely protect whole
    # beats wall-to-wall; a cut is only voided when it would remove the MAJORITY of
    # the protected span. Smaller bites inside a protection are normal editing.
    removes = _clip_by_protected(removes, protected)

    # Audio-truth silence removal: collapse word-free silent spans (false starts,
    # swallowed words, pre-speech lip movement) that inter-word gap tightening misses.
    # Protected beats keep their deliberate silence.
    if silence_spans:
        sil = silence_cut_intervals(
            silence_spans, words, gates_cfg.silence_min_cut_s, gates_cfg.silence_handle_s
        )
        removes += _clip_by_protected(sil, protected)

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

    # v1.6 extract continuity: a topical extract drops the off-topic majority and so leaves many
    # small keep ranges with short gaps between them — which read as explanations severed mid-thought.
    # Bridge the small gaps into a few contiguous blocks (re-admitting the brief sub-second tangents),
    # drop orphan slivers, and snap edges to phrase boundaries. Gated on `extract`, so a normal edit
    # is byte-identical.
    if extract:
        merged = _finalize_extract_blocks(merged, phrases or [], gates_cfg, duration_s)

    # Scoped cold-open: pull ONE strong payoff clip (<=15s) to the very front as a hook.
    # It also stays in its natural position in the body (teaser-then-context). Prepended
    # after the source-order merge so it deliberately breaks monotonic order.
    co = decisions.cold_open or {}
    if "start_s" in co and "end_s" in co and float(co["end_s"]) > float(co["start_s"]):
        cs = max(0.0, float(co["start_s"]))
        ce = min(float(co["end_s"]), cs + 15.0, duration_s)
        snapped = _snap_to_words(cs, ce, words, pad_before, pad_after, duration_s)
        if snapped is not None:
            ns, ne, sh, eh = snapped
            if ne - ns >= 1.0:
                merged.insert(
                    0,
                    EdlRange(
                        start=round(ns, 3), end=round(ne, 3),
                        start_handle_s=round(sh, 3), end_handle_s=round(eh, 3),
                        beat="COLD_OPEN", reason=co.get("reason", "cold-open hook"),
                    ),
                )

    # v0.3.1: a sped range occupies (span / speed) output seconds. speed defaults to 1.0,
    # so this is identical to the old naive sum for any un-sped edit.
    total = sum((r.end - r.start) / (r.speed or 1.0) for r in merged)
    return Edl(
        sources={"camera": source_path},
        ranges=merged,
        total_duration_s=round(total, 2),
    )


def _snap_out_to_phrase(t: float, phrases: list[dict], window: float, bound: float | None, edge: str) -> float:
    """Move a block edge OUTWARD to the nearest phrase boundary within `window`, so a bridged block
    never begins/ends mid-sentence. `bound` caps the move (the neighbour block's edge, or the source
    end); None means clamp only to the source. Returns the (possibly unchanged) boundary."""
    if not phrases:
        return t
    if edge == "start":
        cand = next((p["start"] for p in phrases if p["start"] <= t < p["end"]), None)
        if cand is None:
            return t
        cand = max(cand, 0.0 if bound is None else bound)
        return cand if 0.0 <= t - cand <= window else t
    cand = next((p["end"] for p in phrases if p["start"] < t <= p["end"]), None)
    if cand is None:
        return t
    if bound is not None:
        cand = min(cand, bound)
    return cand if 0.0 <= cand - t <= window else t


def _finalize_extract_blocks(
    ranges: list[EdlRange], phrases: list[dict], gates_cfg: GatesConfig, duration_s: float
) -> list[EdlRange]:
    """v1.6 extract finalize (post-inversion):
    1. Snap each block's edges OUT to the nearest phrase boundary within extract_phrase_snap_window_s
       (bounded by the neighbour block) so a block doesn't start/end mid-sentence.
    2. Drop an isolated block shorter than extract_min_block_s (a topical-extract sliver reads as
       debris; the global min_range_s floor is too low here).
    Gap BRIDGING moved to the remove level in v1.6.3 (so it excludes retakes and lets silence removal
    clean a re-admitted bridge — a post-inversion range merge replayed silence and failed the dead-air
    gate, and could not tell a retake from a cut). Only invoked for an extract."""
    if not ranges:
        return ranges
    blocks = list(ranges)
    win = gates_cfg.extract_phrase_snap_window_s
    for i, r in enumerate(blocks):
        lo = blocks[i - 1].end if i > 0 else None
        hi = blocks[i + 1].start if i + 1 < len(blocks) else duration_s
        ns = _snap_out_to_phrase(r.start, phrases, win, lo, "start")
        ne = _snap_out_to_phrase(r.end, phrases, win, hi, "end")
        if ns < r.start:  # grew earlier to a phrase start: boundary now sits on a word edge
            r.start_handle_s = 0.0
        if ne > r.end:
            r.end_handle_s = 0.0
        r.start, r.end = round(ns, 3), round(ne, 3)
    return [r for r in blocks if r.end - r.start >= gates_cfg.extract_min_block_s]


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


def src_to_out(edl: Edl, raw_s: float) -> float | None:
    """Map a source-timeline second to its OUTPUT (edited-timeline) second, honoring per-range speed.

    v0.3.1: a range played at `speed` occupies (span / speed) output seconds, so BOTH the
    within-segment offset and the cursor advance divide by speed. Dividing only one (e.g. the
    duration sum) silently desyncs anything mapped through here inside a sped beat.

    The COLD_OPEN range is a duplicated payoff clip prepended OUT of source order; it still occupies
    output time (so its duration is added to the cursor) but a beat's natural source position must
    map to its BODY occurrence, not the teaser — otherwise any beat starting before the cold-open's
    source end would wrongly resolve to ~0.0 (it precedes the prepended range in playback order). So
    the cold-open is skipped as a RETURN target while still advancing the cursor. Returns None when
    raw_s lands after the last body range. Used by chapters; cut_transcript() applies the same
    /speed rule for bulk phrase remap (it maps by midpoint containment and keeps cold-open copies)."""
    cursor = 0.0
    for r in edl.ranges:
        sp = r.speed or 1.0
        if (r.beat or "").upper() != "COLD_OPEN" and raw_s <= r.end:
            return cursor + max(0.0, raw_s - r.start) / sp
        cursor += (r.end - r.start) / sp
    return None


def cut_transcript(edl: Edl, phrases: list[dict]) -> list[dict]:
    """Phrases surviving the edit, with output-timeline timestamps (speed-aware; see src_to_out)."""
    out = []
    cursor = 0.0
    for r in edl.ranges:
        sp = r.speed or 1.0
        for p in phrases:
            mid = (p["start"] + p["end"]) / 2
            if r.start <= mid <= r.end:
                out.append(
                    {
                        **p,
                        "out_start": round(cursor + (p["start"] - r.start) / sp, 2),
                        "out_end": round(cursor + (p["end"] - r.start) / sp, 2),
                    }
                )
        cursor += (r.end - r.start) / sp
    return out


def write_benchmark(edl: Edl, run_dir: Path, slug: str) -> Path:
    import json

    path = Path(run_dir) / "final" / "edit-decisions.benchmark.json"
    path.write_text(json.dumps(edl.to_benchmark_format(slug=slug), indent=2))
    return path
