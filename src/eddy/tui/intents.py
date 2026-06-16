"""Turning what the user types in the TUI input bar into a structured Eddy action.

Two layers: `parse_command` is deterministic and instant (Eddy verbs + ``/slash`` commands, no model
call); when it returns None the caller falls back to `interpret_nl`, which asks the local brain to
classify free text into the same `Intent` shape. NL intents (and every long/destructive action) carry
``needs_confirm=True`` so the app always confirms before doing anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
        "note": {"type": "string"},
    },
}

_NL_SYSTEM = (
    "You map a video creator's request to ONE Eddy action. Eddy is a local video editor. "
    "Actions: run (full edit of a footage path; needs source), shorts (vertical clips from a source), "
    "transcribe (a source), render (an existing run), doctor (check setup), runs (list runs), "
    "open (show a run's results; needs run), clean (reclaim a run's scratch; needs run), "
    "purge (delete a run's data; needs run), help, quit. If unsure, use action 'unknown'. "
    "Return JSON with action and any of source/run/target_minutes/note. Never invent a file path."
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
        return " ".join(bits)


def _fail(text: str, note: str) -> Intent:
    return Intent(action="help", needs_confirm=False, source_text=text, note=note, ok=False)


def parse_command(text: str) -> Intent | None:
    """Deterministic parse of a command/slash line. Returns None when it isn't a recognised command
    (so the caller can try natural-language interpretation)."""
    text = text.strip()
    if not text:
        return None

    if text.startswith("/"):
        slash = text[1:].split()[0].lower() if text[1:].split() else ""
        mapping = {"help": "help", "quit": "quit", "exit": "quit", "doctor": "doctor", "runs": "runs"}
        action = mapping.get(slash)
        if action:
            return Intent(action=action, source_text=text)
        return _fail(text, f"unknown command /{slash} — try /help")

    tokens = text.split()
    verb = tokens[0].lower()
    rest = tokens[1:]
    if verb not in ACTIONS:
        return None  # not a command — caller falls back to NL

    args: dict[str, Any] = {}
    flags = [t for t in rest if t.startswith("--")]
    pos = [t for t in rest if not t.startswith("--")]

    if verb in {"run", "shorts", "transcribe"}:
        if not pos:
            return _fail(text, f"{verb} needs a footage path, e.g. {verb} ~/footage/clip.mp4")
        args["source"] = pos[0]
        if verb == "run":
            if len(pos) > 1:
                try:
                    args["target_minutes"] = float(pos[1])
                except ValueError:
                    pass
            args["local_only"] = "--local" in flags or "--local-only" in flags
    elif verb in {"render", "open", "clean", "purge"}:
        if not pos:
            return _fail(text, f"{verb} needs a run slug, e.g. {verb} 2026-06-16-clip")
        args["run"] = pos[0]
        if verb == "purge":
            args["full"] = "--full" in flags

    needs_confirm = verb in LONG_ACTIONS or verb in DESTRUCTIVE_ACTIONS
    return Intent(action=verb, args=args, needs_confirm=needs_confirm, source_text=text)


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
    # NL is best-effort interpretation: always confirm, whatever the action.
    return Intent(action=action, args=args, needs_confirm=True, source_text=text, note=result.get("note", ""))
