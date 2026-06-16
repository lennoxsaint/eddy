"""Parsing the TUI input bar: deterministic command/slash parse first, local-brain NL fallback,
and the safety rule that long + destructive + NL actions all require confirmation."""

from __future__ import annotations

from eddy.tui.intents import Intent, interpret_nl, parse_command


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
