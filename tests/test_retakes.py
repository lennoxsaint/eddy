"""Retake + filler candidate detection on synthetic word timelines.

`retake_candidates` runs on the RAW word timeline: it surfaces repeated 3-7 grams
(with enough information content) that recur within `max_gap_s` — the classic
"oops, let me say that again" pattern. `filler_candidates` flags reset words
("sorry", "okay", "wait"). Both are pure-logic, no media required.
"""

from eddy.edit.retakes import (
    FILLER_RESET_WORDS,
    filler_candidates,
    norm_word,
    retake_candidates,
)


def words_from_phrase(text, *, start=0.0, word_s=0.3, gap_s=0.1):
    """Turn a space-separated phrase into a word timeline starting at `start`."""
    out, t = [], start
    for tok in text.split():
        out.append({"start": round(t, 3), "end": round(t + word_s, 3), "word": f" {tok}", "probability": 0.9})
        t += word_s + gap_s
    return out


def test_clean_speech_yields_no_retakes():
    # all-unique, content-rich words: nothing repeats, so nothing to flag
    words = words_from_phrase("today another building beautiful systems matters greatly indeed always forever")
    assert retake_candidates(words) == []


def test_obvious_retake_repetition_detected():
    first = words_from_phrase("welcome creators building powerful systems", start=0.0)
    # a gap (>1s) then the exact same content phrase restarts
    second = words_from_phrase("welcome creators building powerful systems", start=10.0)
    cands = retake_candidates(first + second)
    assert cands, "a repeated content phrase across a gap must produce a candidate"
    top = cands[0]
    # the two occurrences are paired by their start times, not collapsed to one
    assert top["first_start_s"] < top["second_start_s"]
    assert top["first_start_s"] == 0.0
    assert top["second_start_s"] == 10.0
    # the detected phrase is built from a contiguous slice of normalized content
    assert top["phrase"] in "welcome creators building powerful systems"
    assert "welcome" in top["phrase"]


def test_retake_carries_pause_before_second():
    # the silence right before the restart is the retake tell the model adjudicates on (v1.4 #11)
    first = words_from_phrase("welcome creators building powerful systems", start=0.0)
    second = words_from_phrase("welcome creators building powerful systems", start=10.0)
    top = retake_candidates(first + second)[0]
    assert top["pause_before_second_s"] > 0.5  # ~8s silence before the second take


def test_retake_gap_matches_start_delta():
    first = words_from_phrase("scaling content pipelines daily", start=0.0)
    second = words_from_phrase("scaling content pipelines daily", start=8.0)
    top = retake_candidates(first + second)[0]
    # gap is second_start - first_start, rounded to 0.1s
    assert top["gap_s"] == round(top["second_start_s"] - top["first_start_s"], 1)
    assert top["gap_s"] == 8.0


def test_immediate_repeat_within_one_second_ignored():
    # back-to-back repeat with <=1.0s start delta is filtered (stutter, not a retake)
    first = words_from_phrase("building powerful systems daily", start=0.0, word_s=0.1, gap_s=0.02)
    second = words_from_phrase("building powerful systems daily", start=0.5, word_s=0.1, gap_s=0.02)
    assert retake_candidates(first + second) == []


def test_retake_beyond_max_gap_ignored():
    first = words_from_phrase("designing resilient distributed systems", start=0.0)
    # repeat is 200s later, far beyond the default 120s window
    second = words_from_phrase("designing resilient distributed systems", start=200.0)
    assert retake_candidates(first + second, max_gap_s=120.0) == []
    # but widening the window surfaces it
    assert retake_candidates(first + second, max_gap_s=300.0)


def test_low_information_repeat_not_flagged():
    # phrase made only of stopwords / short tokens: info score < 2, never a candidate
    first = words_from_phrase("we are in the", start=0.0)
    second = words_from_phrase("we are in the", start=10.0)
    assert retake_candidates(first + second) == []


def test_candidates_sorted_by_score_then_gap():
    out = []
    # long, content-dense phrase repeated at a short gap -> high score
    out += words_from_phrase("ambitious creators building powerful resilient systems", start=0.0)
    out += words_from_phrase("ambitious creators building powerful resilient systems", start=6.0)
    # shorter content phrase repeated at a wider gap -> lower score
    out += words_from_phrase("podcast workflow automation", start=40.0)
    out += words_from_phrase("podcast workflow automation", start=90.0)
    cands = retake_candidates(out)
    scores = [c["score"] for c in cands]
    assert scores == sorted(scores, reverse=True)
    # the long, tightly-spaced phrase ranks above the short, far-apart one
    assert cands[0]["score"] >= cands[-1]["score"]
    assert any("ambitious" in c["phrase"] for c in cands)


def test_retake_limit_respected():
    out = []
    # 50 distinct content phrases, each repeated once across a gap
    for i in range(50):
        phrase = f"unique{i}able content phrase marker{i}xyz building"
        out += words_from_phrase(phrase, start=i * 4.0)
        out += words_from_phrase(phrase, start=i * 4.0 + 2.0)
    cands = retake_candidates(out, limit=5)
    assert len(cands) <= 5


def test_filler_reset_words_detected():
    words = words_from_phrase("okay so we keep building wait let me restart sorry", start=0.0)
    fillers = filler_candidates(words)
    found = {f["word"] for f in fillers}
    # every reset marker present in the line is surfaced
    assert FILLER_RESET_WORDS <= found
    # each carries the normalized word + a numeric start time + surrounding context
    for f in fillers:
        assert f["word"] in FILLER_RESET_WORDS
        assert isinstance(f["start_s"], float)
        assert isinstance(f["context"], str) and f["context"]


def test_clean_speech_yields_no_fillers():
    words = words_from_phrase("today we are building resilient content systems together")
    assert filler_candidates(words) == []


def test_filler_punctuation_normalized():
    # "Okay," and "WAIT!" must normalize to the bare reset words and still match
    words = words_from_phrase("Okay, let us continue WAIT! stop here", start=0.0)
    found = {f["word"] for f in filler_candidates(words)}
    assert "okay" in found
    assert "wait" in found
    # norm_word strips case + punctuation deterministically
    assert norm_word("Okay,") == "okay"
    assert norm_word("WAIT!") == "wait"
