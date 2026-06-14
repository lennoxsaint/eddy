"""Deterministic setup→payoff integrity.

Transition / setup phrases ("now let's look at the scripts", "let me show you X") are the
connective tissue that frames the payoff that follows. If a cut removes the setup but keeps the
payoff, the payoff reads as random (the GPT 5.5 output appearing with no introduction). We scan
for these lines and auto-protect them so the model's cuts can't orphan what comes next.
"""

from __future__ import annotations

import re

from eddy.edit.schema import ProtectedMoment

# leading connective/transition cues that introduce a new section or screen
SETUP_PATTERNS = [
    r"\blet'?s (?:look at|take a look|have a look|check out|dive into|talk about|go (?:to|over)|move on|jump (?:to|into))\b",
    r"\b(?:now|next|first|then|so) (?:let'?s|we(?:'| a)re going to|i'?m going to|we'?ll|i'?ll)\b",
    r"\b(?:let me|i(?:'| wi)ll) (?:show you|walk you through|demonstrate|pull up|bring up|read (?:you|out))\b",
    r"\bhere'?s (?:the|what|how|why)\b",
    r"\b(?:if we|let'?s) (?:do|run|try) the same (?:thing|prompt)\b",
]
_RE = re.compile("|".join(SETUP_PATTERNS), re.IGNORECASE)


def setup_protections(phrases: list[dict], pad_s: float = 0.4) -> list[ProtectedMoment]:
    """Short protected moments around setup/transition phrases so cuts can't orphan the
    payoff. Each protection is just the phrase itself (plus a small pad), never a whole beat."""
    out: list[ProtectedMoment] = []
    for p in phrases:
        text = p.get("text", "")
        if _RE.search(text):
            out.append(
                ProtectedMoment(
                    start_s=max(0.0, p["start"] - pad_s),
                    end_s=p["end"] + pad_s,
                    reason=f"setup/transition line: {text[:60]!r}",
                )
            )
    return out
