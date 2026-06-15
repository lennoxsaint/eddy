"""v0.5: property-based fuzz of compile_edl. For ANY random set of cuts, the compiler either
rejects them (CompileError -> routed to the repair loop) or returns an EDL whose ranges are
finite, in-bounds, sorted, non-overlapping, and positive-duration. No adversarial input may
produce a silently-broken EDL (the v0.4 NaN bug is the cautionary tale)."""

import math

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from eddy.config import GatesConfig, RenderConfig
from eddy.edit.compiler import CompileError, compile_edl
from eddy.edit.schema import Cut, EditDecisions, ProtectedMoment

RENDER = RenderConfig()
GATES = GatesConfig()


def _words(n=50, word_s=0.3, gap_s=0.1):
    words, t = [], 0.0
    for i in range(n):
        words.append({"start": round(t, 3), "end": round(t + word_s, 3), "word": f" w{i}", "probability": 0.9})
        t += word_s + gap_s
    return words


WORDS = _words()
DUR = WORDS[-1]["end"] + 1.0

# finite only — NaN/inf are rejected at the schema/parse layer (covered in test_model_boundary).
_f = st.floats(min_value=-5.0, max_value=DUR + 5.0, allow_nan=False, allow_infinity=False)
_pair = st.tuples(_f, _f)


def _assert_valid_edl(edl):
    ranges = edl.ranges
    assert all(math.isfinite(r.start) and math.isfinite(r.end) for r in ranges)
    assert all(r.end > r.start for r in ranges)                       # positive duration
    assert all(r.start >= -0.001 and r.end <= DUR + 0.5 for r in ranges)  # in bounds
    for a, b in zip(ranges, ranges[1:]):                              # sorted + non-overlapping
        assert a.end <= b.start + 1e-6
    assert round(edl.total_duration_s, 3) == round(sum(r.end - r.start for r in ranges), 3)


@settings(max_examples=250, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(st.lists(_pair, max_size=8))
def test_compile_edl_cut_invariants(cut_pairs):
    cuts = [Cut(start_s=min(a, b), end_s=max(a, b) + 0.01, tier="MANDATORY") for a, b in cut_pairs]
    try:
        edl = compile_edl(EditDecisions(cuts=cuts), WORDS, "cam.mp4", DUR, RENDER, GATES, tighten_gaps=False)
    except CompileError:
        return  # rejected-and-routed-to-repair is a valid, safe outcome
    _assert_valid_edl(edl)


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(st.lists(_pair, max_size=5), st.lists(_pair, max_size=3))
def test_compile_edl_with_protected_moments_invariants(cut_pairs, prot_pairs):
    cuts = [Cut(start_s=min(a, b), end_s=max(a, b) + 0.01, tier="RECOMMENDED") for a, b in cut_pairs]
    prot = [ProtectedMoment(start_s=min(a, b), end_s=max(a, b) + 0.01) for a, b in prot_pairs]
    try:
        edl = compile_edl(
            EditDecisions(cuts=cuts, protected_moments=prot), WORDS, "cam.mp4", DUR, RENDER, GATES, tighten_gaps=False
        )
    except CompileError:
        return
    _assert_valid_edl(edl)
