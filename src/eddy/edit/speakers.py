"""v0.8: heuristic multi-speaker detection — WARNING ONLY.

eddy has no diarization (no pyannote / speaker embeddings); it edits assuming a single speaker.
Interview/podcast footage breaks that assumption: cut decisions can sever turn-taking and there's
no per-speaker attribution. We can't *prove* multiple speakers from a mono transcript, so this is a
deliberately conservative heuristic over the transcript text + pause density. It is biased to
UNDER-warn — a false alarm on a monologue is more annoying than a missed interview — and every
finding is labelled as a low/medium-confidence guess, never a fact. Per-speaker EDITING is out of
scope (plan: detection + warning only)."""

from __future__ import annotations

# Framing phrases that strongly imply a second person in the room (host<->guest).
INTERVIEW_CUES = (
    "thanks for having me", "thanks for coming on", "thanks for joining", "welcome to the show",
    "welcome back to the", "my guest", "our guest", "joining me today", "joining us today",
    "great question", "good question", "tell me about", "tell us about",
    "let me ask you", "i want to ask you", "how did you get", "what made you", "walk me through",
    "talk to me about", "appreciate you coming", "for the listeners", "for our listeners",
)


def detect_multispeaker(words: list[dict], *, pause_s: float = 0.8) -> dict:
    """Heuristic. Returns likely_multispeaker + confidence + the signals it saw. Never authoritative."""
    if len(words) < 30:
        return {"likely_multispeaker": False, "confidence": "low", "turns_per_min": 0.0,
                "interview_cues": 0, "reason": "too little speech to judge"}

    duration_min = max((words[-1]["end"] - words[0]["start"]) / 60.0, 0.1)
    long_gaps = sum(1 for a, b in zip(words, words[1:]) if (b["start"] - a["end"]) >= pause_s)
    turns_per_min = long_gaps / duration_min

    # whisper words carry leading spaces; normalize to single-spaced text so multi-word cue
    # phrases match (joining raw with " " would double the spaces and miss every cue).
    text = " ".join(w["word"].strip() for w in words).lower()
    cue_hits = sum(text.count(c) for c in INTERVIEW_CUES)

    # Conservative: the dialogue cues are the strong signal. Pause density alone (breathing,
    # thinking) is NOT enough — it must co-occur with at least one explicit interview cue.
    likely = cue_hits >= 3 or (cue_hits >= 1 and turns_per_min >= 15)
    confidence = "medium" if cue_hits >= 5 else "low"
    return {
        "likely_multispeaker": likely,
        "confidence": confidence,
        "turns_per_min": round(turns_per_min, 1),
        "interview_cues": cue_hits,
        "reason": f"{cue_hits} interview cue(s), ~{turns_per_min:.0f} turns/min",
    }


def multispeaker_warning(detection: dict) -> str | None:
    """A human-readable warning string, or None when nothing to flag."""
    if not detection.get("likely_multispeaker"):
        return None
    return (
        f"Possible multiple speakers ({detection['confidence']} confidence, heuristic: "
        f"{detection['reason']}). eddy edits assuming a SINGLE speaker — it does not diarize or "
        f"attribute lines per speaker, and cuts may break turn-taking. Review interview/podcast "
        f"cuts carefully."
    )
