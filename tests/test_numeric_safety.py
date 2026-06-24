from eddy.config import GatesConfig, RenderConfig
from eddy.edit.compiler import compile_edl
from eddy.edit.numeric_safety import is_numeric_token, needs_numeric_boundary_guard
from eddy.edit.schema import Cut, EditDecisions


def _words(seq, gap=0.10):
    out = []
    t = 0.0
    for word in seq:
        out.append({"word": word, "start": round(t, 3), "end": round(t + 0.18, 3), "probability": 0.99})
        t += 0.18 + gap
    return out


def test_metric_phrase_triggers_numeric_boundary_guard():
    words = _words(["and", "then", "104", "total", "clicks", "moved"])
    assert is_numeric_token("104")
    assert needs_numeric_boundary_guard(words, 2, 4)


def test_compile_edl_gives_metric_boundaries_wider_handles():
    words = _words(["proof", "showed", "104", "total", "clicks", "and", "95", "unique", "clicks", "today"], gap=0.30)
    decisions = EditDecisions(cuts=[Cut(start_s=words[0]["start"], end_s=words[1]["end"], tier="MANDATORY")])
    cfg = RenderConfig(numeric_pad_before_ms=240, numeric_pad_after_ms=360)

    edl = compile_edl(decisions, words, "cam.mp4", words[-1]["end"] + 0.5, cfg, GatesConfig(), tighten_gaps=False)
    first = edl.ranges[0]

    assert first.start_handle_s >= 0.18
    assert first.end_handle_s >= 0.30
