"""v0.8: heuristic multi-speaker detection (warning only). Conservative — biased to under-warn on
monologues; flags interview/podcast framing as a low/medium-confidence guess, never a fact."""

from eddy.edit.speakers import detect_multispeaker, multispeaker_warning


def _words(text, *, gap=0.1):
    """Lay words out end-to-end with a fixed inter-word gap."""
    out, t = [], 0.0
    for w in text.split():
        out.append({"start": t, "end": t + 0.3, "word": " " + w, "probability": 0.9})
        t += 0.3 + gap
    return out


def test_monologue_not_flagged():
    words = _words(("today i want to walk through the system i use to stay focused " * 8))
    det = detect_multispeaker(words)
    assert det["likely_multispeaker"] is False
    assert multispeaker_warning(det) is None


def test_too_short_not_flagged():
    det = detect_multispeaker(_words("hey there welcome"))
    assert det["likely_multispeaker"] is False
    assert "too little speech" in det["reason"]


def test_interview_cues_flag_multispeaker():
    text = (
        "welcome to the show my guest joining me today thanks for having me "
        "great question tell me about how you got started for the listeners "
        + ("we talk about the work " * 20)
    )
    det = detect_multispeaker(_words(text))
    assert det["likely_multispeaker"] is True
    assert det["interview_cues"] >= 3
    w = multispeaker_warning(det)
    assert w is not None and "single speaker" in w.lower()


def test_confidence_scales_with_cues():
    heavy = (
        "thanks for having me my guest our guest joining me today joining us today "
        "great question good question tell me about tell us about "
        + ("conversation continues here " * 20)
    )
    det = detect_multispeaker(_words(heavy))
    assert det["likely_multispeaker"] is True
    assert det["confidence"] == "medium"
