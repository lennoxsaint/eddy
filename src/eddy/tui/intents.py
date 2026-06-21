"""Turning what the user types in the TUI input bar into a structured Eddy action.

Two layers: `parse_command` is deterministic and instant (Eddy verbs + ``/slash`` commands, no model
call); when it returns None the caller falls back to `interpret_nl`, which asks the local brain to
classify free text into the same `Intent` shape. NL intents (and every long/destructive action) carry
``needs_confirm=True`` so the app always confirms before doing anything.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlparse

# verbs that mutate / take minutes and run as background jobs
LONG_ACTIONS = {"run", "shorts", "transcribe", "render"}
DESTRUCTIVE_ACTIONS = {"clean", "purge"}
READ_ACTIONS = {"doctor", "runs", "open", "help", "quit"}
ACTIONS = LONG_ACTIONS | DESTRUCTIVE_ACTIONS | READ_ACTIONS

# JSON schema the local brain fills in when interpreting free text.
INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["action"],
    "properties": {
        "action": {"type": "string", "enum": sorted(ACTIONS | {"unknown"})},
        "source": {"type": "string"},
        "run": {"type": "string"},
        "target_minutes": {"type": "number"},
        "focus": {"type": "string"},
        "note": {"type": "string"},
    },
}

_NL_SYSTEM = (
    "You map a video creator's request to ONE Eddy action. Eddy is a local video editor. "
    "Actions: run (full edit of a footage path; needs source), shorts (vertical clips from a source), "
    "transcribe (a source), render (an existing run), doctor (check setup), runs (list runs), "
    "open (show a run's results; needs run), clean (reclaim a run's scratch; needs run), "
    "purge (delete a run's data; needs run), help, quit. If unsure, use action 'unknown'. "
    "For a 'run', if the user says what to keep/focus the edit on (e.g. 'only the part about X'), "
    "put that verbatim in 'focus'. "
    "Return JSON with action and any of source/run/target_minutes/focus/note. Never invent a file path."
)


@dataclass
class Intent:
    action: str
    args: dict = field(default_factory=dict)
    needs_confirm: bool = False
    source_text: str = ""
    note: str = ""
    ok: bool = True

    def describe(self) -> str:
        """A short human line for the confirm modal / status."""
        if not self.ok:
            return self.note or "couldn't understand that"
        bits = [self.action]
        if self.args.get("source"):
            bits.append(str(self.args["source"]))
        if self.args.get("run"):
            bits.append(str(self.args["run"]))
        if self.args.get("target_minutes"):
            bits.append(f"~{self.args['target_minutes']}min")
        if self.args.get("full"):
            bits.append("--full")
        if self.args.get("local_only"):
            bits.append("--local-only")
        if self.args.get("focus"):
            mode = self.args.get("focus_mode", "steer")
            brief = str(self.args["focus"])
            bits.append(f"[{mode}] {brief[:60]}")
        return " ".join(bits)


def _fail(text: str, note: str) -> Intent:
    return Intent(action="help", needs_confirm=False, source_text=text, note=note, ok=False)


# Natural lead-ins that mean "edit this footage" — so a drag-dropped path reads like plain English
# ("edit this video: <path>") instead of requiring the bare `run` verb. `extract` additionally forces
# the aggressive topical-extract mode.
_EDIT_PREFIX_VERBS = {"edit", "extract"}

# Phrasing that arms EXTRACT mode (keep only the on-topic part, drop the off-topic majority) rather
# than a soft steer. Auto-detection: the user wrote it in plain language, no flag required.
_EXTRACT_CUES = re.compile(
    r"\b(?:"
    r"only (?:keep|show|include|focus|the (?:part|bit|moment|section|portion)|about|on)\b"
    r"|keep only\b|just (?:keep|the (?:part|bit|section))\b|focus only\b"
    r"|(?:cut|remove|drop|delete) everything (?:except|but)\b|everything (?:except|but)\b"
    r"|isolate\b|extract (?:the|my|just|only|out)\b|strictly about\b|nothing (?:but|except)\b"
    r")",
    re.IGNORECASE,
)
_MEDIA_EXT = re.compile(r"\.(?:mp4|mov|mkv|m4v|webm|avi|mp3|m4a|wav|flac|aac|mpg|mpeg)$", re.IGNORECASE)


def is_extract_brief(focus: str | None) -> bool:
    """True when a focus brief is phrased as a hard topical extract ('only keep X') rather than a
    soft steer. Shared by the TUI parser and `eddy run --focus` so both arm extract the same way."""
    return bool(focus and _EXTRACT_CUES.search(focus))


# A creator who writes "a 5-10 minute explanation" or "keep it under 8 minutes" is stating how long
# the cut should run — the deterministic loop should honor that as its target + length ceiling instead
# of falling back to the 12-min default. These read a runtime out of a free-text brief.
_DUR_UNIT = r"(?P<unit>minutes|minute|mins|min|hours|hour|hrs|hr|seconds|second|secs|sec|m|h)"
# Qualifier phrases that make the stated number a CEILING ("under 8 min") rather than a soft target.
_DUR_CAP_QUAL = (
    r"no (?:longer|more) than|shorter than|less than|at most|up to|under|below|within|max(?:imum)?|<=|≤"
)
_DUR_RANGE = re.compile(
    r"(?P<a>\d+(?:\.\d+)?)\s*(?:-|–|—|to|through|thru)\s*(?P<b>\d+(?:\.\d+)?)\s*" + _DUR_UNIT,
    re.IGNORECASE,
)
_DUR_SINGLE = re.compile(
    r"(?P<qual>" + _DUR_CAP_QUAL + r")?\s*(?P<n>\d+(?:\.\d+)?)\s*" + _DUR_UNIT,
    re.IGNORECASE,
)


def _dur_to_min(value: float, unit: str) -> float:
    u = unit.lower()
    if u in ("h", "hr", "hrs", "hour", "hours"):
        return value * 60.0
    if u in ("s", "sec", "secs", "second", "seconds"):
        return value / 60.0
    return value  # minute family


def _sane_band(target_minutes: float, ceiling_minutes: float) -> tuple[float, float] | None:
    """Accept only a plausible extract length (15s–3h) so a stray year/count ('in 2025', 'top 5')
    parsed as a duration is rejected. Clamp the ceiling to ≥ target and ≤ 180 min."""
    t = round(float(target_minutes), 2)
    if not 0.25 <= t <= 180.0:
        return None
    c = round(min(max(float(ceiling_minutes), t), 180.0), 2)
    return t, c


def duration_from_brief(focus: str | None) -> tuple[float, float] | None:
    """Pull an explicit runtime out of a focus brief → (target_minutes, ceiling_minutes), or None.

    Rules: a RANGE ("5-10 min") aims for the top of the range and caps there (never exceed the stated
    upper bound). A capped single ("under 8 min") aims a touch below the cap. A plain single
    ("about a 10 minute cut") targets that length with a small ceiling slack so it isn't a razor-edge
    fail. Returns None when no sane time span is present (caller keeps the configured defaults)."""
    if not focus:
        return None
    text = focus.strip()

    m = _DUR_RANGE.search(text)
    if m:
        a = _dur_to_min(float(m.group("a")), m.group("unit"))
        b = _dur_to_min(float(m.group("b")), m.group("unit"))
        hi = max(a, b)
        return _sane_band(hi, hi)

    m = _DUR_SINGLE.search(text)
    if m:
        n = _dur_to_min(float(m.group("n")), m.group("unit"))
        if m.group("qual"):  # the number is an explicit ceiling
            return _sane_band(round(n * 0.9, 2), n)
        return _sane_band(n, round(n * 1.15, 2))
    return None


def normalize_source(raw: str) -> str:
    """Turn a dragged/pasted/typed path token into a real local path. Handles a macOS Finder
    drag-drop (backslash-escaped spaces), one surrounding quote pair, and a file:// URL. Does NOT
    expanduser — the run path does that later — so '~/clip.mp4' stays as typed."""
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    if s.lower().startswith("file://"):
        s = unquote(urlparse(s).path)
    # undo Finder-style backslash escapes (space, parens, &, etc.) but leave a literal Windows '\' alone
    s = re.sub(r"\\([ ()\[\]{}'\"&!#$;`*?])", r"\1", s)
    return s.strip()


def _looks_like_path(tok: str) -> bool:
    t = tok.strip().strip("'\"")
    if t.lower().startswith("file://"):
        return True
    if t.startswith(("/", "~", "./", "../")):
        return True
    if "/" in t and " " not in t:
        return True
    return bool(_MEDIA_EXT.search(t))


def _split_focus(text: str) -> tuple[str, str | None]:
    """Split a command line into (head, focus brief). The brief is everything after the FIRST
    ' - ' (space-hyphen-space). A Finder drag-drop escapes path spaces as '\\ ', so a real ' - ' is
    the user's separator, never part of the path. Documented rule: first ' - ' wins."""
    if " - " in text:
        head, tail = text.split(" - ", 1)
        tail = tail.strip()
        return head.strip(), (tail or None)
    return text.strip(), None


def _attach_focus(args: dict[str, Any], focus: str | None, *, force_extract: bool) -> None:
    if not focus:
        return
    args["focus"] = focus
    args["focus_mode"] = "extract" if (force_extract or is_extract_brief(focus)) else "steer"


def parse_command(text: str) -> Intent | None:
    """Deterministic parse of a command/slash line. Returns None when it isn't a recognised command
    (so the caller can try natural-language interpretation)."""
    text = text.strip()
    if not text:
        return None

    # a /slash command is a single "/word" — NOT an absolute path like /Users/me/clip.mp4 (which
    # has a second '/' or a media extension and should be treated as a dropped footage path).
    first_tok = text.split()[0] if text.split() else ""
    if text.startswith("/") and "/" not in first_tok[1:] and not _MEDIA_EXT.search(first_tok):
        slash = first_tok[1:].lower()
        mapping = {"help": "help", "quit": "quit", "exit": "quit", "doctor": "doctor", "runs": "runs"}
        action = mapping.get(slash)
        if action:
            return Intent(action=action, source_text=text)
        return _fail(text, f"unknown command /{slash} — try /help")

    # peel off the free-text focus brief BEFORE tokenizing, so its apostrophes/punctuation never
    # break shlex and never get mistaken for path tokens.
    head, focus = _split_focus(text)
    try:
        # shlex so a quoted / backslash-escaped path with spaces survives a Finder drag-drop;
        # fail soft to a naive split on an unbalanced quote so a paste can never crash the parse.
        tokens = shlex.split(head, posix=True)
    except ValueError:
        tokens = head.split()
    if not tokens:
        return None

    verb = tokens[0].lower()

    # 1) natural lead-in: "edit this video: <path>" / "extract <path>"
    if verb in _EDIT_PREFIX_VERBS:
        path_idx = next((i for i in range(1, len(tokens)) if _looks_like_path(tokens[i])), None)
        if path_idx is None:
            return _fail(text, "edit needs a footage path — drag a video in, e.g. edit this video: ~/clip.mp4")
        args: dict[str, Any] = {"source": normalize_source(tokens[path_idx])}
        # no ' - ' brief? trailing plain words after the path become the focus ("edit <path> only the intro")
        if focus is None:
            trailing = [t for t in tokens[path_idx + 1:] if not t.startswith("--")]
            if trailing:
                focus = " ".join(trailing).strip() or None
        args["local_only"] = "--local" in tokens or "--local-only" in tokens
        _attach_focus(args, focus, force_extract=(verb == "extract"))
        return Intent(action="run", args=args, needs_confirm=True, source_text=text)

    # 2) classic verb grammar
    if verb in ACTIONS:
        rest = tokens[1:]
        flags = [t for t in rest if t.startswith("--")]
        pos = [t for t in rest if not t.startswith("--")]
        args = {}
        if verb in {"run", "shorts", "transcribe"}:
            if not pos:
                return _fail(text, f"{verb} needs a footage path, e.g. {verb} ~/footage/clip.mp4")
            args["source"] = normalize_source(pos[0])
            if verb == "run":
                if len(pos) > 1:
                    try:
                        args["target_minutes"] = float(pos[1])
                    except ValueError:
                        pass
                args["local_only"] = "--local" in flags or "--local-only" in flags
                _attach_focus(args, focus, force_extract=False)
        elif verb in {"render", "open", "clean", "purge"}:
            if not pos:
                return _fail(text, f"{verb} needs a run slug, e.g. {verb} 2026-06-16-clip")
            args["run"] = pos[0]
            if verb == "purge":
                args["full"] = "--full" in flags
        needs_confirm = verb in LONG_ACTIONS or verb in DESTRUCTIVE_ACTIONS
        return Intent(action=verb, args=args, needs_confirm=needs_confirm, source_text=text)

    # 3) a bare dropped path with no verb ("~/clip.mp4 - only the codex bit") = edit that file
    if _looks_like_path(tokens[0]):
        args = {
            "source": normalize_source(tokens[0]),
            "local_only": "--local" in tokens or "--local-only" in tokens,
        }
        _attach_focus(args, focus, force_extract=False)
        return Intent(action="run", args=args, needs_confirm=True, source_text=text)

    return None  # not a command — caller falls back to NL


def interpret_nl(text: str, provider: Any) -> Intent:
    """Ask the local brain to classify free text into an Intent. Always needs confirmation. Degrades
    gracefully (ok=False) when there's no brain or the result is unusable."""
    if provider is None:
        return _fail(text, "no local brain available to interpret that — try a command or /help")
    try:
        result = provider.complete(
            [{"role": "system", "content": _NL_SYSTEM}, {"role": "user", "content": text}],
            schema=INTENT_SCHEMA,
        )
    except Exception as e:  # any provider/parse failure → graceful fallback
        return _fail(text, f"couldn't interpret that ({type(e).__name__}) — try a command or /help")

    action = str(result.get("action", "unknown"))
    if action == "unknown" or action not in ACTIONS:
        return _fail(text, result.get("note") or "not sure what you mean — try a command or /help")

    args: dict[str, Any] = {}
    if result.get("source"):
        args["source"] = result["source"]
    if result.get("run"):
        args["run"] = result["run"]
    if isinstance(result.get("target_minutes"), (int, float)):
        args["target_minutes"] = float(result["target_minutes"])
    if action == "run" and result.get("focus"):
        _attach_focus(args, str(result["focus"]), force_extract=False)
    # NL is best-effort interpretation: always confirm, whatever the action.
    return Intent(action=action, args=args, needs_confirm=True, source_text=text, note=result.get("note", ""))
