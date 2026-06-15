"""Setup/transition phrase auto-protection (setup_protections).

enforce_protection_budget is covered in test_aggressive_cut.py — not duplicated here.
"""

import pytest

from eddy.edit.protect import setup_protections
from eddy.edit.schema import ProtectedMoment


def phrase(start, end, text):
    return {"start": start, "end": end, "text": text}


def test_plain_phrases_yield_no_protections():
    phrases = [
        phrase(0.0, 2.0, "the weather was nice that morning"),
        phrase(2.0, 4.0, "I poured myself a coffee and sat down"),
        phrase(4.0, 6.0, "it ran for about an hour"),
    ]
    assert setup_protections(phrases) == []


def test_setup_line_produces_one_protection():
    phrases = [
        phrase(0.0, 2.0, "intro words here we go"),
        phrase(2.0, 4.0, "now let's look at the scripts"),
        phrase(4.0, 6.0, "and here is the actual script content"),
    ]
    prot = setup_protections(phrases)
    assert len(prot) == 1
    assert isinstance(prot[0], ProtectedMoment)
    assert "scripts" in prot[0].reason


def test_protection_span_pads_around_only_the_setup_phrase():
    phrases = [
        phrase(2.0, 4.0, "let me show you the dashboard"),
    ]
    (pm,) = setup_protections(phrases)
    # default pad is 0.4s on each side of the phrase boundaries
    assert pm.start_s == 2.0 - 0.4
    assert pm.end_s == 4.0 + 0.4
    # span is the phrase (2s) plus both pads — never a whole beat
    assert pm.end_s - pm.start_s == pytest.approx(2.0 + 0.8)


def test_custom_pad_respected():
    phrases = [phrase(5.0, 7.0, "here's the why behind it")]
    (pm,) = setup_protections(phrases, pad_s=1.5)
    assert pm.start_s == 5.0 - 1.5
    assert pm.end_s == 7.0 + 1.5


def test_pad_clamped_at_zero_start():
    phrases = [phrase(0.1, 2.0, "now let's dive into the code")]
    (pm,) = setup_protections(phrases, pad_s=0.4)
    # 0.1 - 0.4 would be negative; must clamp to 0.0
    assert pm.start_s == 0.0
    assert pm.end_s == 2.0 + 0.4


def test_only_matching_phrases_are_protected():
    phrases = [
        phrase(0.0, 2.0, "I was thinking about this all week"),
        phrase(2.0, 4.0, "so let's take a look at what happened"),
        phrase(4.0, 6.0, "the results were surprising honestly"),
        phrase(6.0, 8.0, "let me walk you through the numbers"),
    ]
    prot = setup_protections(phrases)
    assert len(prot) == 2
    # the two protections cover the matching phrases, not the plain ones
    covered = [(p.start_s, p.end_s) for p in prot]
    assert any(s <= 3.0 <= e for s, e in covered)  # phrase 2.0-4.0
    assert any(s <= 7.0 <= e for s, e in covered)  # phrase 6.0-8.0
    # the plain phrase at 1.0 / 5.0 is not covered by any protection
    assert not any(s <= 1.0 <= e for s, e in covered)
    assert not any(s <= 5.0 <= e for s, e in covered)


def test_matching_is_case_insensitive():
    phrases = [phrase(0.0, 2.0, "HERE'S THE THING ABOUT THIS")]
    prot = setup_protections(phrases)
    assert len(prot) == 1


def test_reason_truncates_long_text_to_60_chars():
    long_text = "now let's look at " + ("x" * 200)
    phrases = [phrase(0.0, 2.0, long_text)]
    (pm,) = setup_protections(phrases)
    # reason embeds repr of the first 60 chars of the phrase text
    assert repr(long_text[:60]) in pm.reason
    assert repr(long_text) not in pm.reason


def test_missing_text_key_is_ignored():
    # a phrase dict with no "text" key must not raise and must not protect
    phrases = [{"start": 0.0, "end": 2.0}]
    assert setup_protections(phrases) == []


def test_substring_setup_cue_inside_longer_phrase_matches():
    phrases = [
        phrase(0.0, 3.0, "okay so first let's go to the settings page real quick"),
    ]
    prot = setup_protections(phrases)
    assert len(prot) == 1
    assert prot[0].start_s <= 1.5 <= prot[0].end_s
