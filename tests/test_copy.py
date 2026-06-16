"""Packaging copy: deterministic chapter derivation + description assembly.

Chapter TIMESTAMPS are derived mechanically from the beat map mapped onto the
OUTPUT timeline (src_to_out); only the LABELS come from the model. These tests
build synthetic Edl + EditDecisions(x_eddy.beats) and assert the timestamps are
deterministic (monotonic, output-mapped, first pinned to 0.0, near-duplicates
dropped) and that the description carries the chapters block.
"""

from eddy.edit.schema import Edl, EdlRange
from eddy.package.copy import (
    _fmt_ts,
    chapters,
    chapters_block,
    description,
    titles,
)


class _Receipts:
    """Captures logged events so fallback paths are observable."""

    def __init__(self):
        self.events = []

    def log(self, event, **fields):
        self.events.append((event, fields))


class _LabelProvider:
    """Returns one model label per beat, in order."""

    def __init__(self, labels):
        self._labels = labels
        self.calls = []

    def complete(self, messages, schema=None, max_tokens=None):
        self.calls.append(messages)
        return {"labels": list(self._labels)}


class _DeadProvider:
    def complete(self, *a, **k):
        raise RuntimeError("provider down")


def _decisions(beats):
    class _Eddy:
        pass

    class _D:
        x_eddy = _Eddy()

    _D.x_eddy.beats = beats
    return _D


def _single_range_edl():
    """One un-sped keep range covering source 0..120s. With no cut and speed 1.0,
    output time == source time, so beat start_s map straight through src_to_out."""
    return Edl(
        sources={"camera": "cam.mp4"},
        ranges=[EdlRange(source="camera", start=0.0, end=120.0, speed=1.0)],
        total_duration_s=120.0,
    )


def test_fmt_ts_minutes_and_hours():
    assert _fmt_ts(0) == "0:00"
    assert _fmt_ts(75) == "1:15"
    assert _fmt_ts(3661) == "1:01:01"  # rolls over into the h:mm:ss form


def test_chapters_empty_when_no_beats():
    edl = _single_range_edl()
    provider = _LabelProvider([])
    rcpt = _Receipts()
    assert chapters(edl, _decisions([]), provider, rcpt) == []
    # no beats -> model is never consulted
    assert provider.calls == []


def test_chapter_timestamps_are_output_mapped_and_first_pinned():
    edl = _single_range_edl()
    beats = [
        {"label": "intro", "start_s": 5.0, "summary": "warmup"},
        {"label": "core", "start_s": 40.0, "summary": "the idea"},
        {"label": "wrap", "start_s": 90.0, "summary": "recap"},
    ]
    provider = _LabelProvider(["Opening Move", "The Core Idea", "Wrapping Up"])
    chaps = chapters(edl, _decisions(beats), provider, _Receipts())

    assert len(chaps) == 3
    # first chapter is always pinned to 0.0 regardless of the beat's source start
    assert chaps[0]["out_s"] == 0.0
    # un-sped single range: later beats map straight onto the output timeline
    assert chaps[1]["out_s"] == 40.0
    assert chaps[2]["out_s"] == 90.0
    # labels come from the model, attached in beat order
    assert [c["label"] for c in chaps] == ["Opening Move", "The Core Idea", "Wrapping Up"]


def test_chapter_timestamps_monotonic_and_drop_near_duplicates():
    edl = _single_range_edl()
    # 7.0 is < 10s after 0.0's pinned anchor -> the second beat is dropped
    beats = [
        {"label": "a", "start_s": 0.0, "summary": "s0"},
        {"label": "b", "start_s": 7.0, "summary": "s1"},  # too close to first -> dropped
        {"label": "c", "start_s": 60.0, "summary": "s2"},
    ]
    provider = _LabelProvider(["Alpha", "Charlie"])  # only two survive
    chaps = chapters(edl, _decisions(beats), provider, _Receipts())

    outs = [c["out_s"] for c in chaps]
    assert outs == [0.0, 60.0]
    assert outs == sorted(outs)  # monotonic non-decreasing
    # every adjacent pair is the required 10s apart
    assert all(b - a >= 10 for a, b in zip(outs, outs[1:]))
    assert [c["label"] for c in chaps] == ["Alpha", "Charlie"]


def test_speed_compresses_chapter_output_time():
    # a 2x range plays in half the output seconds, so a beat at source 60s maps to ~30s out.
    edl = Edl(
        sources={"camera": "cam.mp4"},
        ranges=[EdlRange(source="camera", start=0.0, end=120.0, speed=2.0)],
        total_duration_s=60.0,
    )
    beats = [
        {"label": "intro", "start_s": 0.0, "summary": "s0"},
        {"label": "later", "start_s": 60.0, "summary": "s1"},
    ]
    provider = _LabelProvider(["Intro", "Later"])
    chaps = chapters(edl, _decisions(beats), provider, _Receipts())
    assert chaps[0]["out_s"] == 0.0
    assert chaps[1]["out_s"] == 30.0  # 60s source / 2x speed = 30s output


def test_chapter_label_fallback_titles_beat_when_model_fails():
    edl = _single_range_edl()
    beats = [
        {"label": "first_beat", "start_s": 0.0, "summary": "s0"},
        {"label": "second_beat", "start_s": 50.0, "summary": "s1"},
    ]
    rcpt = _Receipts()
    chaps = chapters(edl, _decisions(beats), _DeadProvider(), rcpt)

    # fallback derives labels deterministically from the beat slug
    assert [c["label"] for c in chaps] == ["First Beat", "Second Beat"]
    # timestamps are unaffected by the label fallback
    assert [c["out_s"] for c in chaps] == [0.0, 50.0]
    # the fallback is recorded as a receipt
    assert any(ev == "chapter_labels_fallback" for ev, _ in rcpt.events)


def test_chapters_block_renders_timestamp_then_label():
    chaps = [
        {"out_s": 0.0, "label": "Opening Move"},
        {"out_s": 90.0, "label": "Wrapping Up"},
        {"out_s": 3661.0, "label": "Bonus"},
    ]
    block = chapters_block(chaps)
    assert block.splitlines() == [
        "0:00 Opening Move",
        "1:30 Wrapping Up",
        "1:01:01 Bonus",
    ]


def test_description_includes_chapters_block_and_cta(monkeypatch, tmp_path):
    # avoid reading the real prompt file from disk; the function only concatenates it
    monkeypatch.setattr(
        "eddy.package.copy.PROMPTS", tmp_path, raising=True
    )
    (tmp_path / "description.md").write_text("PROMPT")

    chaps = [
        {"out_s": 0.0, "label": "Opening Move"},
        {"out_s": 90.0, "label": "The Payoff"},
    ]
    block = chapters_block(chaps)

    # model returns prose that OMITS the chapters block -> code must append it
    class _DescProvider:
        def complete(self, messages, schema=None, max_tokens=None):
            self.seen = messages[0]["content"]
            return {"description": "Line one.\nLine two about the video."}

    provider = _DescProvider()
    kept_phrases = [{"text": "we open"}, {"text": "we pay off"}]
    desc = description(
        kept_phrases, chaps, provider, _Receipts(), cta="Join at example.com/plans"
    )

    # the deterministic chapters block survives into the final description
    assert "0:00 Opening Move" in desc
    assert "1:30 The Payoff" in desc
    assert block in desc
    # the CTA was passed into the prompt the model saw
    assert "Join at example.com/plans" in provider.seen


def test_description_strips_em_dashes():
    chaps = [{"out_s": 0.0, "label": "Start"}]

    class _EmDashProvider:
        def complete(self, messages, schema=None, max_tokens=None):
            return {"description": "before—after"}

    desc = description([{"text": "x"}], chaps, _EmDashProvider(), _Receipts())
    assert "—" not in desc
    assert "before - after" in desc


def test_titles_fallback_when_model_fails(monkeypatch, tmp_path):
    # a brain hiccup must NOT fail the whole launch kit — titles fall back to grounded keyphrases
    monkeypatch.setattr("eddy.package.copy.PROMPTS", tmp_path, raising=True)
    (tmp_path / "titles.md").write_text("PROMPT")
    rcpt = _Receipts()
    kept = [
        {"text": "the single biggest mistake creators make with their hooks"},
        {"text": "ok"},  # too short to become a title
        {"text": "why your first three seconds decide everything"},
    ]
    out = titles(kept, _DeadProvider(), rcpt)
    assert out and all("title" in t and "grounding_quote" in t for t in out)
    assert "—" not in out[0]["title"]  # still em-dash-free
    # longest substantive phrase becomes the top candidate
    assert out[0]["title"].startswith("the single biggest mistake")
    assert any(ev == "titles_fallback" for ev, _ in rcpt.events)
    assert any(ev == "titles" for ev, _ in rcpt.events)


def test_titles_fallback_handles_no_usable_phrases():
    out = titles([{"text": "hi"}], _DeadProvider(), _Receipts())
    assert len(out) == 1 and out[0]["title"] == "Untitled edit"


def test_description_fallback_when_model_fails(monkeypatch, tmp_path):
    monkeypatch.setattr("eddy.package.copy.PROMPTS", tmp_path, raising=True)
    (tmp_path / "description.md").write_text("PROMPT")
    chaps = [{"out_s": 0.0, "label": "Start"}, {"out_s": 90.0, "label": "The Payoff"}]
    rcpt = _Receipts()
    desc = description(
        [{"text": "we open the video here"}, {"text": "we wrap up"}],
        chaps, _DeadProvider(), rcpt, cta="Join at example.com/plans",
    )
    assert "0:00 Start" in desc and "1:30 The Payoff" in desc  # chapters block survives
    assert "Join at example.com/plans" in desc  # CTA preserved
    assert "we open the video here" in desc  # lead drawn from the transcript
    assert any(ev == "description_fallback" for ev, _ in rcpt.events)
