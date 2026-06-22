"""Friendly phase labels for the TUI: known engine slugs become plain language, the edit loop folds to
one 'Editing' step, failures aren't numbered, and unknown slugs degrade to a title-cased label."""

from __future__ import annotations

from eddy.tui import phases


def test_known_phases_get_plain_labels():
    assert phases.friendly("studio_sound") == "Polishing audio"
    assert phases.friendly("final_render") == "Rendering video"
    assert phases.friendly("done") == "Done"


def test_iteration_collapses_to_editing_with_pass_number():
    assert phases.friendly("iteration_2") == "Editing (pass 2)"
    # every editing pass folds onto the single 'editing' major step (step 2 of N)
    assert "step 2 of" in phases.progress("iteration_5")
    assert phases.progress("iteration_1") == phases.progress("loop_done")


def test_failure_phase_labelled_but_not_numbered():
    assert phases.friendly("loop_failed_no_edl") == "Editing failed"
    assert phases.progress("loop_failed_no_edl") == ""


def test_unknown_phase_is_title_cased_not_hidden():
    assert phases.friendly("some_new_phase") == "Some new phase"
    assert phases.progress("some_new_phase") == ""


def test_empty_and_placeholder():
    assert phases.friendly(None) == "Starting…"
    assert phases.friendly("?") == "Starting…"
    assert phases.progress(None) == ""


def test_label_combines_friendly_and_step():
    lab = phases.label("final_render")
    assert lab.startswith("Rendering video") and "step" in lab


# --- per-run plan: honest 'step k of N' instead of a fixed 10 -------------------------------------

_VIDEO_PLAN = ["transcribe", "editing", "ship_panel", "final_render", "done"]  # a 'just the video' run


def test_progress_counts_against_the_run_plan_not_the_fixed_ten():
    # the SAME phase reads as 'of 5' on this run and 'of 10' with no plan (the old behaviour)
    assert phases.progress("iteration_2", _VIDEO_PLAN) == "(step 2 of 5)"
    assert phases.progress("final_render", _VIDEO_PLAN) == "(step 4 of 5)"
    assert "of 10" in phases.progress("final_render")  # no plan -> static fallback


def test_progress_shorts_only_plan_is_four_steps():
    plan = ["transcribe", "editing", "shorts", "done"]
    assert phases.progress("plan", plan) == "(step 2 of 4)"  # the shorts 'plan' phase folds to editing
    assert phases.progress("shorts", plan) == "(step 3 of 4)"


def test_breadcrumb_marks_done_current_and_pending():
    bc = phases.breadcrumb("iteration_2", _VIDEO_PLAN)
    assert "✓ Transcribe" in bc          # a completed stage
    assert "▸ Editing (pass 2)" in bc    # the current stage shows the live pass number
    assert "Final checks" in bc and "Render" in bc and "Done" in bc  # what's left
    # the current stage is the only one with the ▸ marker
    assert bc.count("▸") == 1


def test_breadcrumb_failed_phase_is_blank():
    assert phases.breadcrumb("loop_failed_no_edl", _VIDEO_PLAN) == ""
