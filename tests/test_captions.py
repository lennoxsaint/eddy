from __future__ import annotations

import importlib.util
from pathlib import Path

from eddy.proof import caption_terminal_punctuation_verdict


ROOT = Path(__file__).resolve().parents[1]


def _karaoke_module():
    spec = importlib.util.spec_from_file_location("karaoke_ass", ROOT / "scripts" / "karaoke_ass.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_caption_tokens_preserve_sentence_endings_without_visual_noise() -> None:
    karaoke = _karaoke_module()

    assert karaoke.esc("finished.") == "finished."
    assert karaoke.esc("really?") == "really?"
    assert karaoke.esc("yes!") == "yes!"
    assert karaoke.esc("you...") == "you."
    assert karaoke.esc("5.2,") == "5.2"
    assert karaoke.esc("'quoted,'") == "quoted"


def test_caption_punctuation_gate_rejects_stripped_sentence_endings() -> None:
    planned = [
        {"word": "This"},
        {"word": "works."},
        {"word": "Really?"},
        {"word": "Yes!"},
    ]

    stripped = caption_terminal_punctuation_verdict(
        planned,
        ["This", "works", "Really", "Yes"],
    )
    preserved = caption_terminal_punctuation_verdict(
        planned,
        ["This", "works.", "Really?", "Yes!"],
    )

    assert stripped["pass"] is False
    assert stripped["reason"] == "caption_terminal_punctuation_missing"
    assert preserved == {
        "pass": True,
        "reason": None,
        "expected_terminal_marks": 3,
        "mismatches": [],
    }


def test_karaoke_ass_contains_terminal_punctuation_in_every_word_state() -> None:
    karaoke = _karaoke_module()
    words = [
        {"word": "This", "start": 0.0, "end": 0.2},
        {"word": "works.", "start": 0.2, "end": 0.5},
    ]

    ass = karaoke.build(words, 1080, 1920, 1155, 68, 5, True)

    assert "WORKS." in ass
    assert "WORKS{" not in ass


def test_progressive_karaoke_never_shows_future_words() -> None:
    karaoke = _karaoke_module()
    words = [
        {"word": "Prior", "start": 0.0, "end": 0.2},
        {"word": "Active", "start": 0.2, "end": 0.4},
        {"word": "Future", "start": 0.4, "end": 0.6},
    ]

    events = [
        line
        for line in karaoke.build(words, 1080, 1920, 1155, 68, 5, True).splitlines()
        if line.startswith("Dialogue:")
    ]

    assert "ACTIVE" not in events[0]
    assert "FUTURE" not in events[0]
    assert "PRIOR" in events[1] and "ACTIVE" in events[1]
    assert "FUTURE" not in events[1]
