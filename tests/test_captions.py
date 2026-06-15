"""Karaoke caption grouping + timing invariants on synthetic word lists.

We exercise the pure logic (group_cues / caption_events / word_width) and never
render real video. PNG writes and font measurement are mocked where they would
otherwise depend on installed fonts or touch disk, so grouping thresholds are
deterministic and the timing math is asserted directly.
"""

from __future__ import annotations

import pytest

from eddy.render import captions as C
from eddy.render import layout as L


def make_words(texts, *, word_s=0.3, gap_s=0.1, start=0.0):
    """One word dict per text, each word_s long with gap_s between."""
    words, t = [], start
    for txt in texts:
        words.append({"start": round(t, 3), "end": round(t + word_s, 3), "word": txt})
        t += word_s + gap_s
    return words


@pytest.fixture
def fixed_width(monkeypatch):
    """Make word_width deterministic: 10px per character (post-strip).

    group_cues adds a 24px inter-word gap, so cue width is predictable and the
    CUE_MAX_PX break can be triggered precisely.
    """
    monkeypatch.setattr(C, "word_width", lambda word, font: 10 * len(word.strip()))


@pytest.fixture
def no_png(monkeypatch):
    """Stub PNG rendering so caption_events does no font load / disk image write."""
    calls = []
    monkeypatch.setattr(C, "render_caption_png", lambda path, cue, idx: calls.append((path, len(cue), idx)))
    return calls


# --- word_width: real font, relative assertions (no tautology) ---


def test_word_width_longer_text_is_wider():
    font = C.load_font(L.CAPTION_FONT_S)
    assert C.word_width("antidisestablishment", font) > C.word_width("hi", font)
    assert C.word_width("hi", font) > 0


def test_word_width_is_case_insensitive_via_upper():
    # word_width uppercases internally, so case of input must not change the result.
    font = C.load_font(L.CAPTION_FONT_S)
    assert C.word_width("hello", font) == C.word_width("HELLO", font)


# --- group_cues: 3-6 word groups, break on count / duration / width ---


def test_group_cues_breaks_at_six_words(fixed_width):
    # ultra-short words so neither duration (CUE_MAX_S) nor width caps trigger first;
    # only the 6-word count cap can split this.
    words = make_words([f"w{i}" for i in range(8)], word_s=0.05, gap_s=0.0)
    cues = C.group_cues(words)
    assert [len(c) for c in cues] == [L.CUE_MAX_WORDS, 8 - L.CUE_MAX_WORDS]
    assert max(len(c) for c in cues) == L.CUE_MAX_WORDS  # never exceeds the word cap
    flat = [w["word"] for c in cues for w in c]
    assert flat == [w["word"] for w in words]  # every word preserved, in order


def test_group_cues_breaks_on_duration_before_word_cap(fixed_width):
    # 0.7s words, no gap: by the 3rd word the cue would span 2.1s >= CUE_MAX_S, so the
    # duration cap splits cues well before the 6-word count cap is ever reached.
    words = make_words([f"w{i}" for i in range(6)], word_s=0.7, gap_s=0.0)
    cues = C.group_cues(words)
    assert all(len(c) < L.CUE_MAX_WORDS for c in cues)  # count cap never reached
    # a new cue is opened only when ADDING the next word would push span past CUE_MAX_S,
    # so within any cue the span up to its last-but-one word stays under the cap
    for cue in cues:
        if len(cue) >= 2:
            span_without_last = cue[-2]["end"] - cue[0]["start"]
            assert span_without_last < L.CUE_MAX_S


def test_group_cues_breaks_on_width(fixed_width):
    # 4 words of 25 chars each = 250px + 24px gaps; 4 words = 1000+72 = 1072 > 930px cap
    big = "x" * 25
    words = make_words([big, big, big, big])
    cues = C.group_cues(words)
    assert len(cues) > 1
    # no single cue may exceed the pixel cap (10px/char model + 24px gaps)
    for cue in cues:
        width = sum(10 * len(w["word"]) for w in cue) + 24 * (len(cue) - 1)
        assert width <= L.CUE_MAX_PX


def test_group_cues_preserves_all_words_and_order(fixed_width):
    words = make_words([f"w{i}" for i in range(15)])
    cues = C.group_cues(words)
    flat = [w["word"] for c in cues for w in c]
    assert flat == [w["word"] for w in words]
    assert all(1 <= len(c) <= L.CUE_MAX_WORDS for c in cues)


# --- caption_events: one event per word, karaoke timing, monotonic ---


def test_caption_events_one_event_per_word(no_png, tmp_path, fixed_width):
    words = make_words([f"w{i}" for i in range(7)])
    events = C.caption_events(tmp_path, words)
    assert len(events) == len(words)
    assert len(no_png) == len(words)  # one PNG render per word-state


def test_caption_events_karaoke_handoff_within_cue(no_png, tmp_path, fixed_width):
    # 4 short words -> single cue. Each non-final word's end == next word's start.
    words = make_words(["a", "b", "c", "d"])
    events = C.caption_events(tmp_path, words)
    for i in range(len(events) - 1):
        assert events[i]["end"] == pytest.approx(events[i + 1]["start"], abs=1e-6)


def test_caption_events_last_word_holds_after_end(no_png, tmp_path, fixed_width):
    words = make_words(["a", "b", "c"])
    events = C.caption_events(tmp_path, words)
    last_word, last_event = words[-1], events[-1]
    # final word lingers ~0.24s past its spoken end
    assert last_event["end"] == pytest.approx(last_word["end"] + 0.24, abs=1e-6)


def test_caption_events_starts_are_monotonic_and_nonzero_duration(no_png, tmp_path, fixed_width):
    # interleave overlapping words to try to force a backwards start; clamp must hold
    words = [
        {"start": 0.0, "end": 0.50, "word": "one"},
        {"start": 0.40, "end": 0.45, "word": "two"},  # starts before prev end + is short
        {"start": 0.30, "end": 0.60, "word": "three"},  # deliberately earlier start
        {"start": 1.00, "end": 1.20, "word": "four"},
    ]
    events = C.caption_events(tmp_path, words)
    starts = [e["start"] for e in events]
    assert starts == sorted(starts)  # never goes backwards despite messy input
    for e in events:
        assert e["end"] - e["start"] >= 0.12 - 1e-9  # minimum visible duration enforced


def test_caption_events_paths_unique_per_word(no_png, tmp_path, fixed_width):
    words = make_words([f"w{i}" for i in range(9)])  # spans >1 cue at 6-word cap
    events = C.caption_events(tmp_path, words)
    paths = [str(e["path"]) for e in events]
    assert len(set(paths)) == len(paths)  # no two word-states collide on disk
    assert all("caption-states" in p for p in paths)
