"""_run_plan: the ordered stages a run will actually execute, so the TUI shows an honest 'step k of N'
(a 'just the video' run is fewer stages than a full kit, and optional stages follow config flags)."""

from __future__ import annotations

from eddy.config import EddyConfig
from eddy.loop.controller import _run_plan


def test_video_only_skips_shorts_and_titles():
    # defaults: ship_panel + studio_sound on, aggressive_trim + speed_ramp off
    plan = _run_plan(EddyConfig(), skip_shorts=True, skip_package=True)
    assert plan == ["transcribe", "editing", "ship_panel", "final_render", "studio_sound", "first_60_motion", "done"]
    assert "shorts" not in plan and "package" not in plan  # the source of the old 'of 10' lie


def test_full_kit_keeps_shorts_and_titles():
    plan = _run_plan(EddyConfig(), skip_shorts=False, skip_package=False)
    assert plan[-3:] == ["shorts", "package", "done"]


def test_optional_stages_follow_config_flags():
    cfg = EddyConfig()
    cfg.loop.enable_aggressive_trim = True
    cfg.loop.enable_speed_ramp = True
    cfg.loop.ship_panel = False
    cfg.audio.studio_sound = False
    cfg.motion.mode = "off"
    plan = _run_plan(cfg, skip_shorts=True, skip_package=True)
    assert "trim_to_fit" in plan and "speed_to_fit" in plan
    assert "ship_panel" not in plan and "studio_sound" not in plan
    assert plan[0] == "transcribe" and plan[-1] == "done"
