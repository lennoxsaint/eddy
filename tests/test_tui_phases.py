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
