"""Map Eddy's internal pipeline phase slugs to friendly, human labels for the TUI.

The engine names phases for itself (`trim_to_fit`, `studio_sound`, `iteration_2`, …; see
`eddy.loop.controller`). A non-technical creator shouldn't have to read those. `friendly()` turns a raw
phase into a plain label; `progress()` gives a "(step k of N)" sense from the major-phase order (the
variable-length editing loop collapses to one "Editing" step).
"""

from __future__ import annotations

# Major pipeline phases in order, with friendly labels. The iteration_N loop folds onto "editing".
_ORDER: tuple[tuple[str, str], ...] = (
    ("transcribe", "Transcribing"),
    ("editing", "Editing"),
    ("trim_to_fit", "Trimming to length"),
    ("speed_to_fit", "Fitting length"),
    ("ship_panel", "Final checks"),
    ("final_render", "Rendering video"),
    ("studio_sound", "Polishing audio"),
    ("shorts", "Making shorts"),
    ("package", "Writing titles & description"),
    ("done", "Done"),
)
_LABEL = dict(_ORDER)
_KEYS = [k for k, _ in _ORDER]

# Raw phase slugs that fold onto a major-phase key (the edit loop's transient terminals + the
# shorts-only fast path's planning step).
_ALIASES = {
    "plan": "editing",
    "loop_done": "editing",
    "loop_done_best_attempt": "editing",
}

# Terminal failure phases — labelled plainly, and never counted as a numbered step.
_FAIL = {"loop_failed_no_edl": "Editing failed"}


def _key(phase: str) -> str:
    if phase.startswith("iteration_"):
        return "editing"
    return _ALIASES.get(phase, phase)


def friendly(phase: str | None) -> str:
    """A plain-language label for a raw phase slug (unknown slugs are title-cased, not hidden)."""
    if not phase or phase == "?":
        return "Starting…"
    if phase in _FAIL:
        return _FAIL[phase]
    if phase.startswith("iteration_"):
        n = phase.split("_", 1)[1]
        return f"Editing (pass {n})" if n.isdigit() else "Editing"
    key = _key(phase)
    if key in _LABEL:
        return _LABEL[key]
    return phase.replace("_", " ").capitalize()


def progress(phase: str | None) -> str:
    """'(step k of N)' for phases on the main path; '' for failures or off-path phases."""
    if not phase or phase in _FAIL:
        return ""
    key = _key(phase)
    return f"(step {_KEYS.index(key) + 1} of {len(_KEYS)})" if key in _KEYS else ""


def label(phase: str | None) -> str:
    """`friendly` + a trailing '(step k of N)' when on the main path — what the monitor shows."""
    base = friendly(phase)
    prog = progress(phase)
    return f"{base}  {prog}" if prog else base
