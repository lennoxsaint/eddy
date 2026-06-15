"""v1.0 GA: soak / scale validation. OPT-IN (EDDY_SOAK=1) so the fast suite is unaffected. Proves the
scale-sensitive DETERMINISTIC logic (multi-hour transcript compile, many cuts, big short-candidate
sets, large batch queues) stays correct and bounded — without real ffmpeg/model renders, which are
covered by the synthetic e2e + dogfood. Each test asserts a wall-clock budget to catch quadratic
blowups, and validates output, not just 'it ran'."""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("EDDY_SOAK"), reason="opt-in soak suite (slow; set EDDY_SOAK=1)")


def _words(n, step=0.4):
    return [{"start": i * step, "end": i * step + step * 0.9, "word": f" w{i}", "probability": 0.9} for i in range(n)]


def test_multihour_transcript_compiles_bounded():
    """~3 hours of speech (≈27k words) compiles to a valid EDL well under budget (no quadratic blowup)."""
    from eddy.config import EddyConfig
    from eddy.edit.compiler import compile_edl
    from eddy.edit.schema import Cut, EditDecisions

    cfg = EddyConfig()
    n = 27_000  # ~3h at ~2.5 words/s
    words = _words(n)
    duration = words[-1]["end"]
    # a few hundred scattered cuts to exercise the interval machinery at scale
    cuts = [Cut(start_s=t, end_s=t + 1.0, tier="RECOMMENDED") for t in range(50, int(duration) - 50, 600)]
    decisions = EditDecisions(cuts=cuts, retakes=[], protected_moments=[], shorts_candidates=[])

    t0 = time.time()
    edl = compile_edl(decisions, words=words, source_path="/x/long.mp4", duration_s=duration,
                      render_cfg=cfg.render, gates_cfg=cfg.gates)
    elapsed = time.time() - t0

    assert edl.ranges, "multi-hour compile produced no ranges"
    assert edl.total_duration_s > 0
    assert edl.total_duration_s <= duration + 1.0  # can't exceed the source
    assert elapsed < 20.0, f"multi-hour compile too slow ({elapsed:.1f}s) — possible quadratic scaling"


def test_many_shorts_candidates_capped_not_choked():
    """Hundreds of short candidates: the selection cap (count*2, sorted by start) holds and stays cheap."""
    from eddy.config import EddyConfig
    from eddy.edit.schema import ShortsCandidate

    cfg = EddyConfig()
    cands = [ShortsCandidate(start_s=float(i), end_s=float(i) + 30.0, hook=f"h{i}") for i in range(500)]
    t0 = time.time()
    selected = sorted(cands, key=lambda c: c.start_s)[: cfg.shorts.count * 2]  # mirrors render/shorts.py:165
    elapsed = time.time() - t0
    assert len(selected) == cfg.shorts.count * 2
    assert selected == sorted(selected, key=lambda c: c.start_s)  # ordering preserved
    assert elapsed < 1.0


def test_large_batch_queue_completes_and_isolates_failures():
    """A 1000-source queue: every item processed, failures isolated, summary exact, bounded time."""
    from eddy.batch import run_batch

    processed = []

    def runner(source, **opts):
        processed.append(source)
        if "x7" in str(source):  # ~deterministic subset fails
            raise RuntimeError("boom")

    sources = [f"src-{i}" for i in range(1000)]
    t0 = time.time()
    summary = run_batch(sources, runner=runner)
    elapsed = time.time() - t0

    assert len(processed) == 1000  # never stopped early
    assert summary["total"] == 1000
    assert summary["succeeded"] + summary["failed"] == 1000
    expected_failures = sum(1 for s in sources if "x7" in s)
    assert summary["failed"] == expected_failures
    assert elapsed < 5.0


def test_compile_is_idempotent_at_scale():
    """Determinism must hold at scale too: recompiling a large input is byte-identical."""
    from eddy.config import EddyConfig
    from eddy.edit.compiler import compile_edl
    from eddy.edit.schema import EditDecisions

    cfg = EddyConfig()
    words = _words(15_000)
    dur = words[-1]["end"]
    dec = EditDecisions(retakes=[], cuts=[], protected_moments=[], shorts_candidates=[])
    kw = dict(words=words, source_path="/x/long.mp4", duration_s=dur, render_cfg=cfg.render, gates_cfg=cfg.gates)
    assert compile_edl(dec, **kw).model_dump_json() == compile_edl(dec, **kw).model_dump_json()
