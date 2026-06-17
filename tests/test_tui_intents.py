"""Parsing the TUI input bar: deterministic command/slash parse first, local-brain NL fallback,
and the safety rule that long + destructive + NL actions all require confirmation."""

from __future__ import annotations

from eddy.tui.intents import Intent, interpret_nl, is_extract_brief, normalize_source, parse_command


def test_run_command_parses_source_and_confirms():
    i = parse_command("run ~/footage/clip.mp4")
    assert i.action == "run" and i.args["source"] == "~/footage/clip.mp4"
    assert i.needs_confirm is True


def test_run_with_minutes_and_local_flag():
    i = parse_command("run footage/ 12 --local")
    assert i.args["target_minutes"] == 12.0 and i.args["local_only"] is True


def test_read_commands_do_not_confirm():
    for cmd in ("doctor", "runs", "help"):
        i = parse_command(cmd)
        assert i.action == cmd and i.needs_confirm is False


def test_destructive_commands_confirm():
    assert parse_command("clean myrun").needs_confirm is True
    p = parse_command("purge myrun --full")
    assert p.action == "purge" and p.args["full"] is True and p.needs_confirm is True


def test_missing_argument_fails_gracefully():
    i = parse_command("run")
    assert i.ok is False and "footage" in i.note


def test_slash_commands():
    assert parse_command("/quit").action == "quit"
    assert parse_command("/doctor").action == "doctor"
    bad = parse_command("/wat")
    assert bad.ok is False and "unknown" in bad.note


def test_non_command_returns_none_for_nl_fallback():
    assert parse_command("make my podcast punchy please") is None


def test_interpret_nl_maps_provider_result():
    class FakeProvider:
        def complete(self, messages, schema=None):
            return {"action": "run", "source": "~/pod.mp4", "target_minutes": 10}

    i = interpret_nl("edit my podcast", FakeProvider())
    assert i.action == "run" and i.args["source"] == "~/pod.mp4"
    assert i.args["target_minutes"] == 10.0 and i.needs_confirm is True  # NL always confirms


def test_interpret_nl_no_provider():
    i = interpret_nl("do something", None)
    assert i.ok is False and "no local brain" in i.note


def test_interpret_nl_unknown_action():
    class FakeProvider:
        def complete(self, messages, schema=None):
            return {"action": "unknown", "note": "huh"}

    assert interpret_nl("xyzzy", FakeProvider()).ok is False


def test_interpret_nl_provider_error_is_graceful():
    class Boom:
        def complete(self, messages, schema=None):
            raise RuntimeError("offline")

    i = interpret_nl("anything", Boom())
    assert i.ok is False and "couldn't interpret" in i.note


def test_describe_is_readable():
    i = Intent(action="run", args={"source": "a.mp4", "target_minutes": 8}, needs_confirm=True)
    assert "run" in i.describe() and "a.mp4" in i.describe()


# --- v1.5 drag-drop + focus brief ----------------------------------------------------------------

def test_drag_dropped_path_with_escaped_spaces_survives():
    # macOS Finder drag-drop escapes spaces with a backslash; shlex must keep the path whole.
    i = parse_command(r"run /Users/me/My\ Videos/clip\ final.mp4")
    assert i.action == "run" and i.args["source"] == "/Users/me/My Videos/clip final.mp4"


def test_quoted_path_with_spaces_survives():
    i = parse_command("run '/Users/me/My Videos/clip.mp4'")
    assert i.args["source"] == "/Users/me/My Videos/clip.mp4"


def test_file_url_is_normalized_to_local_path():
    s = normalize_source("file:///Users/me/My%20Videos/clip.mp4")
    assert s == "/Users/me/My Videos/clip.mp4"


def test_edit_this_video_natural_grammar_with_focus():
    i = parse_command(
        "edit this video: /Users/me/codex-call.mp4 - i want this video to only focus on my Codex explanation"
    )
    assert i.action == "run"
    assert i.args["source"] == "/Users/me/codex-call.mp4"
    assert i.args["focus"] == "i want this video to only focus on my Codex explanation"
    assert i.args["focus_mode"] == "extract"  # 'only focus on' arms extract
    assert i.needs_confirm is True


def test_soft_steer_brief_is_not_extract():
    i = parse_command("run ~/talk.mp4 - center it on the pricing story and trim the tangents")
    assert i.args["focus_mode"] == "steer"


def test_extract_verb_forces_extract_even_without_cue():
    i = parse_command("extract ~/talk.mp4 - the pricing story")
    assert i.action == "run" and i.args["focus_mode"] == "extract"


def test_bare_dropped_path_is_an_edit():
    i = parse_command("/Users/me/codex-call.mp4 - only keep the demo")
    assert i.action == "run" and i.args["source"] == "/Users/me/codex-call.mp4"
    assert i.args["focus_mode"] == "extract"


def test_first_dash_separates_path_from_brief():
    # the brief may itself contain ' - '; only the first split matters
    i = parse_command("edit ~/v.mp4 - keep only intro - and the outro")
    assert i.args["source"] == "~/v.mp4"
    assert i.args["focus"] == "keep only intro - and the outro"


def test_is_extract_brief_phrasing():
    assert is_extract_brief("only keep the part where I explain Codex")
    assert is_extract_brief("just the bit about pricing")
    assert is_extract_brief("cut everything except the demo")
    assert not is_extract_brief("make it punchier and tighten the pacing")
    assert not is_extract_brief(None)


def test_focus_only_attaches_to_run_not_other_verbs():
    # a focus brief on a non-run verb is ignored (no focus plumbing for transcribe/shorts)
    i = parse_command("transcribe ~/v.mp4 - only the intro")
    assert i.action == "transcribe" and "focus" not in i.args
