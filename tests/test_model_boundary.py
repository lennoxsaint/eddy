"""v0.4: the model boundary is adversarial. NaN/inf timestamps must never reach the renderer.

Regression for the critical bug where a `NaN` cut bound passed every compiler range guard
(all NaN comparisons are False) and silently deleted content from 0.0 with no error.
Three independent layers: provider JSON parse, pydantic schema, and the compiler (which routes
a non-finite interval into the repair loop instead of cutting on it).
"""

import math

import pytest
from pydantic import ValidationError

from eddy.config import GatesConfig, RenderConfig
from eddy.edit.compiler import CompileError, compile_edl
from eddy.edit.schema import Cut, EditDecisions, EdlRange, ProtectedMoment, Retake
from eddy.providers.base import ProviderError, extract_json

RENDER = RenderConfig()
GATES = GatesConfig()


def _words(n=12, word_s=0.3, gap_s=0.1):
    words, t = [], 0.0
    for i in range(n):
        words.append({"start": round(t, 3), "end": round(t + word_s, 3), "word": f" w{i}", "probability": 0.9})
        t += word_s + gap_s
    return words


# --- layer 1: provider JSON boundary -------------------------------------------------

@pytest.mark.parametrize("blob", ['{"start_s": NaN}', '{"x": Infinity}', '{"y": -Infinity}'])
def test_extract_json_rejects_nonfinite_constants(blob):
    with pytest.raises(ProviderError):
        extract_json(blob)


def test_extract_json_still_parses_normal_objects():
    assert extract_json('```json\n{"a": 1, "b": 2.5}\n```') == {"a": 1, "b": 2.5}


# --- v1.6: salvage a TRUNCATED cut list (long extract overran num_predict) ------------

def test_extract_json_repairs_truncated_cut_list():
    # the model emitted a valid object but ran out of tokens mid-way through a later cut object
    truncated = '{"cuts": [{"start_s": 1, "end_s": 2}, {"start_s": 3, "end_s": 4}, {"start_s": 5, "end'
    out = extract_json(truncated)
    # the complete elements survive; the half-written trailing object is dropped, not crashed on
    assert out == {"cuts": [{"start_s": 1, "end_s": 2}, {"start_s": 3, "end_s": 4}]}


def test_extract_json_repair_preserves_outer_keys_before_the_open_array():
    truncated = '{"target": 9, "cuts": [{"start_s": 1, "end_s": 2}, {"start_s": 3, "en'
    out = extract_json(truncated)
    assert out == {"target": 9, "cuts": [{"start_s": 1, "end_s": 2}]}


def test_extract_json_brace_inside_string_is_not_miscounted():
    # a '}' inside a quoted value must not be read as a structural close
    assert extract_json('{"quote": "a } b", "n": 1}') == {"quote": "a } b", "n": 1}


def test_extract_json_unsalvageable_truncation_still_raises():
    # truncated before any nested element completed -> nothing safe to keep
    with pytest.raises(ProviderError, match="unterminated"):
        extract_json('{"cuts": [{"start_s": 1, "end')


# --- layer 2: pydantic schema --------------------------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_cut_rejects_nonfinite(bad):
    with pytest.raises(ValidationError):
        Cut(start_s=bad, end_s=10.0, tier="MANDATORY")


@pytest.mark.parametrize("model,kwargs", [
    (Retake, {"remove_start_s": float("nan"), "remove_end_s": 1.0}),
    (ProtectedMoment, {"start_s": float("inf"), "end_s": 1.0}),
    (EdlRange, {"start": float("nan"), "end": 1.0}),
])
def test_other_models_reject_nonfinite(model, kwargs):
    with pytest.raises(ValidationError):
        model(**kwargs)


def test_editdecisions_validate_rejects_nan_from_raw_model_output():
    raw = {
        "cuts": [{"start_s": float("nan"), "end_s": 10.0, "tier": "MANDATORY"}],
        "retakes": [], "protected_moments": [], "shorts_candidates": [],
    }
    with pytest.raises(ValidationError):
        EditDecisions.model_validate(raw)


# --- layer 3: compiler routes a non-finite interval to repair (defense in depth) -----

def test_compile_edl_routes_nonfinite_interval_to_repair():
    words = _words()
    dur = words[-1]["end"] + 1.0
    # bypass schema validation to prove the compiler is independently safe (e.g. a future
    # code path that builds decisions without re-validating).
    nan_cut = Cut.model_construct(start_s=float("nan"), end_s=10.0, quote="", reason="", tier="MANDATORY")
    d = EditDecisions.model_construct(cuts=[nan_cut], retakes=[], protected_moments=[], shorts_candidates=[])
    with pytest.raises(CompileError) as exc:
        compile_edl(d, words, "cam.mp4", dur, RENDER, GATES, tighten_gaps=False)
    assert any(p["type"] == "non_finite_interval" for p in exc.value.problems)


def test_compile_edl_still_compiles_a_clean_cut():
    words = _words()
    dur = words[-1]["end"] + 1.0
    d = EditDecisions(cuts=[Cut(start_s=words[4]["start"], end_s=words[6]["end"], tier="MANDATORY")])
    edl = compile_edl(d, words, "cam.mp4", dur, RENDER, GATES, tighten_gaps=False)
    assert len(edl.ranges) == 2
    assert all(math.isfinite(r.start) and math.isfinite(r.end) for r in edl.ranges)
