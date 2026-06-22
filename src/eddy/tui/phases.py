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

# Terser labels for the inline stage breadcrumb (the full friendly labels are too wide in a row).
_SHORT = {
    "transcribe": "Transcribe",
    "editing": "Edit",
    "trim_to_fit": "Trim",
    "speed_to_fit": "Fit length",
    "ship_panel": "Final checks",
    "final_render": "Render",
    "studio_sound": "Audio",
    "shorts": "Shorts",
    "package": "Titles",
    "done": "Done",
}

_GOLD = "#f5b836"  # brand gold; kept inline so this module stays Textual-free (the engine imports it)

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


def progress(phase: str | None, plan: list[str] | None = None) -> str:
    """'(step k of N)' against THIS run's plan (the stages it will actually run); falls back to the
    full static order when no plan was recorded. '' for failures or off-path phases."""
    if not phase or phase in _FAIL:
        return ""
    keys = plan or _KEYS
    key = _key(phase)
    return f"(step {keys.index(key) + 1} of {len(keys)})" if key in keys else ""


def label(phase: str | None, plan: list[str] | None = None) -> str:
    """`friendly` + a trailing '(step k of N)' when on the main path — the one-line status form."""
    base = friendly(phase)
    prog = progress(phase, plan)
    return f"{base}  {prog}" if prog else base


def breadcrumb(phase: str | None, plan: list[str] | None = None) -> str:
    """A one-line 'where am I in the whole run' trail: done stages ✓ (green), the current stage ▸
    (gold, showing the live editing pass), and what's left (dim). Rendered against the run's actual
    plan, so a 'just the video' run shows its real ~5 stages, not a fixed 10. '' for a failed phase."""
    if phase and phase in _FAIL:
        return ""
    keys = plan or _KEYS
    cur = keys.index(_key(phase)) if phase and _key(phase) in keys else -1
    parts: list[str] = []
    for i, k in enumerate(keys):
        lbl = _SHORT.get(k, _LABEL.get(k, k))
        if i < cur:
            parts.append(f"[green]✓ {lbl}[/]")
        elif i == cur:
            cur_lbl = friendly(phase) if k == "editing" else lbl  # show 'Editing (pass N)' live
            parts.append(f"[{_GOLD} bold]▸ {cur_lbl}[/]")
        else:
            parts.append(f"[dim]{lbl}[/]")
    return "   ".join(parts)
