"""The Eddy home screen: animated eaglet header, a runs list, a live run monitor, and a bottom input
bar that takes Eddy commands, /slash commands, or plain-language requests (interpreted by the local
brain, always confirmed). A 2s poll keeps the runs list + monitor + the eaglet's mood live.

The copy is deliberately calm: a warm one-screen welcome (not a CLI cheat-sheet), engine phases shown
as plain labels, and run quality led by a human verdict — the raw judge/gates numbers are demoted.
"""

from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual import on, work
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.suggester import Suggester
from textual.widgets import DataTable, Footer, Input, Static

from eddy.tui import phases
from eddy.tui.intents import ACTIONS, Intent, interpret_nl, parse_command
from eddy.tui.runner import TuiData, run_verdict
from eddy.tui.screens.confirm import ConfirmScreen
from eddy.tui.screens.output import OUTPUT_FLAGS, OutputScreen
from eddy.tui.screens.doctor import DoctorScreen
from eddy.tui.screens.failure import FailureScreen
from eddy.tui.screens.preview import PreviewScreen
from eddy.tui.widgets.eagle import EagleWidget

_GOLD = "#f5b836"
_DIM = "#8b909b"

# A warm, minimal welcome — the first thing a (non-technical) creator sees. Plain words, one obvious
# first action. The full command reference lives in _HELP (shown on /help or F1).
_WELCOME = (
    f"[{_GOLD} bold]Hi, I'm Eddy.[/] Drop in a video and I'll turn it into a finished YouTube kit —\n"
    "privately, on your own machine. I check with you before anything big.\n\n"
    "Just tell me what you want — in plain words or a command:\n\n"
    f"  [{_GOLD}]run my footage[/]      edit a video start to finish\n"
    f"  [{_GOLD}]shorts my footage[/]   make vertical shorts from it\n"
    f"  [{_GOLD}]open a run[/]          show me a finished result\n\n"
    f"[{_DIM}]Type /help for everything. F1 help · F2 doctor · ctrl+c quit.[/]"
)

# The full reference, shown on /help or F1 — keeps the power-user verbs (transcribe/clean/purge).
_HELP = (
    f"[{_GOLD} bold]Eddy — commands[/]   (or just ask in plain words)\n\n"
    "  run <footage> [minutes]   edit a video start to finish\n"
    "  shorts <footage>          make vertical shorts\n"
    "  transcribe <footage>      transcript only\n"
    "  render <run>              re-render an existing run\n"
    "  open <run>                show + reveal a run's results\n"
    "  clean <run>               reclaim a run's scratch space\n"
    "  purge <run>               delete a run's data (asks first)\n"
    "  doctor · runs · /help · /quit\n\n"
    f"[{_DIM}]Keys: F5 refresh · F4 preview · F3 why-failed · F2 doctor · F1 help · ctrl+x cancel · ctrl+c quit.[/]"
)


def _complete_path(frag: str) -> str | None:
    """Filesystem completion that EXTENDS the typed fragment (Textual requires the suggestion to start
    with what's typed, so we keep the user's `~`/relative form rather than switching to absolute)."""
    expanded = Path(frag).expanduser()
    if frag.endswith("/"):
        base, prefix, typed_dir = expanded, "", frag
    else:
        base, prefix = expanded.parent, expanded.name
        typed_dir = frag[: len(frag) - len(prefix)]  # the dir part, verbatim as typed
    try:
        names = sorted(p.name + ("/" if p.is_dir() else "") for p in base.iterdir() if p.name.startswith(prefix))
    except OSError:
        return None
    return typed_dir + names[0] if names else None


class _CmdSuggester(Suggester):
    """Inline ghost-completion for the command bar: filesystem paths for the footage verbs, run slugs
    for the run verbs, and the verb vocabulary otherwise. Submission still goes through parse_command."""

    def __init__(self, slugs) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self._slugs = slugs  # callable -> current run slugs

    async def get_suggestion(self, value: str) -> str | None:
        if not value or value.startswith("/"):
            return None
        parts = value.split()
        verb, mid = parts[0].lower(), value.endswith(" ")
        if len(parts) == 1 and not mid:  # completing the verb itself
            for cand in sorted(ACTIONS):
                if cand.startswith(verb) and cand != verb:
                    return cand
            return None
        frag = parts[-1]
        head = value[: value.rfind(frag)]
        if verb in {"run", "shorts", "transcribe"} and len(parts) >= 2 and not mid:
            comp = _complete_path(frag)
            return head + comp if comp else None
        if verb in {"render", "open", "clean", "purge"} and len(parts) >= 2 and not mid:
            for slug in self._slugs():
                if slug.lower().startswith(frag.lower()):
                    return head + slug
        return None


class HomeScreen(Screen):
    BINDINGS = [
        ("f5", "refresh", "Refresh"),
        ("f4", "preview", "Preview"),
        ("f3", "why_failed", "Why?"),
        ("f2", "doctor", "Doctor"),
        ("f1", "help", "Help"),
        ("ctrl+x", "cancel_run", "Cancel"),
    ]

    def __init__(self, data: TuiData) -> None:
        super().__init__()
        self.data = data
        self._selected: str | None = None
        self._was_running = False
        self._slugs: list[str] = []
        self._notified_fail: set[str] = set()
        self._last_failed: str | None = None

    def compose(self):
        with Horizontal(id="hdr"):
            yield EagleWidget(small=True, id="eagle")
            yield Static(id="title")
        with Horizontal(id="main"):
            yield DataTable(id="runs", cursor_type="row")
            yield Static(f"[{_DIM}]No edits yet —\ntype: run my footage[/]", id="runsempty")
            yield VerticalScroll(Static(_WELCOME, id="monitor"), id="monitorwrap")
        yield Input(placeholder="What should Eddy do?  (try: run my footage)", id="cmd",
                    suggester=_CmdSuggester(lambda: self._slugs))
        yield Footer()

    def on_mount(self) -> None:
        from eddy import __version__

        self.query_one("#title", Static).update(
            f"[{_GOLD} bold]EDDY[/]  [{_DIM}]· local-first agentic video editor[/]\n"
            f"[{_DIM}]brain: {self.data.brain_label()} · v{__version__}[/]"
        )
        table = self.query_one("#runs", DataTable)
        table.add_columns("run", "phase")
        table.border_title = "runs"
        self._refresh_table()
        self.set_interval(2.0, self._poll)
        self.query_one("#cmd", Input).focus()

    # --- runs list ---------------------------------------------------------------------------------
    def _refresh_table(self) -> None:
        runs = self.data.runs()
        self._slugs = [r["slug"] for r in runs]
        table = self.query_one("#runs", DataTable)
        empty = self.query_one("#runsempty", Static)
        table.display = bool(runs)
        empty.display = not runs
        if not runs:
            return
        prev = self._selected
        table.clear()
        for r in runs:
            table.add_row(r["slug"], phases.friendly(r.get("phase")), key=r["slug"])
        if prev and prev in self._slugs:
            try:
                table.move_cursor(row=table.get_row_index(prev))
            except Exception:
                pass

    def action_refresh(self) -> None:
        self._refresh_table()
        self._status("refreshed")

    @on(DataTable.RowHighlighted, "#runs")
    def _row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key and event.row_key.value:
            self._selected = event.row_key.value
            self._update_monitor(self._selected)

    def _update_monitor(self, slug: str) -> None:
        d = self.data.run_detail(slug)
        st = d["state"]
        lines = [f"[{_GOLD} bold]{escape(slug)}[/]", phases.label(st.get("phase"))]
        verdict = run_verdict(st)
        if verdict:
            lines.append(verdict)
        attempts = st.get("attempts") or []
        if attempts:  # raw engine numbers, demoted to a dim secondary line for power users
            a = attempts[-1]
            lines.append(
                f"[{_DIM}]iter {a.get('iteration', '?')} · q{a.get('quality', 0):.2f} · "
                f"judge {a.get('judge_score', 0):.1f} · gates {'✓' if a.get('gates_passed') else '✗'}[/]"
            )
        if self.data.is_interrupted(slug):
            lines.append(f"[{_GOLD}]interrupted — type: render {escape(slug)} to resume[/]")
        if slug in self._notified_fail:
            lines.append("[red]failed — press F3 for what went wrong[/]")
        if d["artifacts"]:
            lines.append("")
            lines.append(f"[{_DIM}]results:[/] {escape(', '.join(d['artifacts'][:12]))}")
        if any(j.get("job_id") == slug and j.get("state") == "running" for j in self.data.jobs_status()):
            tail = self.data.log_tail(slug, 10)
            if tail:
                lines.append("")
                lines.append(f"[{_DIM}]{escape(tail)}[/]")
        titles = self.data.artifact_text(slug, "titles.md")
        if titles:
            lines.append("")
            lines.append(f"[{_DIM}]titles:[/]\n{escape(titles[:600])}")
        self.query_one("#monitor", Static).update("\n".join(lines))

    # --- input / intents ---------------------------------------------------------------------------
    @on(Input.Submitted, "#cmd")
    def _on_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.query_one("#cmd", Input).value = ""
        if not text:
            return
        intent = parse_command(text)
        if intent is None:  # not a command — let the brain interpret it
            self._set_eagle("thinking")
            self._status(f"interpreting “{text}”…")
            self._interpret(text)
            return
        self._handle_intent(intent)

    @work(thread=True, exclusive=True)
    def _interpret(self, text: str) -> None:
        from eddy.tui.runner import local_provider

        intent = interpret_nl(text, local_provider())  # local brain only — never a billable cloud call
        self.app.call_from_thread(self._handle_intent, intent)

    def _handle_intent(self, intent: Intent) -> None:
        self._set_eagle("idle")
        if not intent.ok:
            self._status(intent.note)
            return
        a = intent.action
        if a == "quit":
            self.app.exit()
            return
        if a == "help":
            self.query_one("#monitor", Static).update(_HELP)
            return
        if a == "runs":
            self.action_refresh()
            return
        if a == "doctor":
            self.app.push_screen(DoctorScreen())
            return
        if a == "open":
            slug = intent.args.get("run")
            if slug:
                self._selected = slug
                self._update_monitor(slug)
                self.app.push_screen(PreviewScreen(self.data, slug))  # in-app preview (works headless)
                if self.data.reveal(slug):
                    self._status(f"opened {slug}")
                else:
                    # honest: don't claim we opened it if there's no OS opener — give the path
                    path = self.data.results_path(slug)
                    self._status(f"results at {path}" if path else f"{slug} has no results yet")
            return
        if intent.needs_confirm:
            # a focused / extract edit asks what to PRODUCE (Lennox picks each time); the chooser
            # doubles as the confirm. Every other mutating action uses the plain yes/no confirm.
            if a == "run" and intent.args.get("focus"):
                self.app.push_screen(
                    OutputScreen(intent.describe()), lambda choice: self._exec_with_output(choice, intent)
                )
            else:
                self.app.push_screen(ConfirmScreen(intent.describe()), lambda ok: self._maybe_exec(ok, intent))
        else:
            self._exec(intent)

    def _maybe_exec(self, ok: bool | None, intent: Intent) -> None:
        if ok:
            self._exec(intent)
        else:
            self._status("cancelled")

    def _exec_with_output(self, choice: str | None, intent: Intent) -> None:
        if not choice:
            self._status("cancelled")
            return
        intent.args["skip_shorts"], intent.args["skip_package"] = OUTPUT_FLAGS[choice]
        self._exec(intent)

    @work(thread=True)
    def _exec(self, intent: Intent) -> None:
        try:
            res = self.data.execute(intent)
        except Exception as e:
            self.app.call_from_thread(self._status, f"failed: {e}")
            return
        self.app.call_from_thread(self._after_exec, res)

    def _after_exec(self, res: dict) -> None:
        if res.get("msg"):
            self._status(res["msg"])
        self._refresh_table()
        if res.get("job_id"):
            self._selected = res["job_id"]
            self._set_eagle("working")

    # --- cancel ------------------------------------------------------------------------------------
    def action_cancel_run(self) -> None:
        slug = self._selected
        if not slug:
            self._status("select a run first, then ctrl+x to cancel")
            return
        if not any(j.get("job_id") == slug and j.get("state") == "running" for j in self.data.jobs_status()):
            self._status(f"{slug} isn't running")
            return
        self.app.push_screen(ConfirmScreen(f"cancel {slug}?"), lambda ok: self._do_cancel(ok, slug))

    def _do_cancel(self, ok: bool | None, slug: str) -> None:
        if ok:
            self.data.cancel(slug)
            self._status(f"cancelling {slug}")
            self._refresh_table()
        else:
            self._status("kept running")

    # --- polling / status --------------------------------------------------------------------------
    def _poll(self) -> None:
        self._refresh_table()
        running = self.data.any_running()
        eagle = self.query_one("#eagle", EagleWidget)
        if running:
            self._was_running = True
            eagle.set_state("working")
        elif self._was_running:
            self._was_running = False
            self._show_finish(eagle)
        if self._selected:
            self._update_monitor(self._selected)

    def _show_finish(self, eagle: EagleWidget) -> None:
        """Eaglet tells the truth: a failed run shows the sad bird + a notify, not the happy one."""
        new_failures = [j for j in self.data.failed_jobs() if j["job_id"] not in self._notified_fail]
        if new_failures:
            eagle.set_state("error")
            for j in new_failures:
                self._notified_fail.add(j["job_id"])
                self._last_failed = j["job_id"]
                self._status(f"{j['job_id']} failed — press F3 for what went wrong")
            delay = 5.0
        else:
            eagle.set_state("success")
            delay = 3.0
        self.set_timer(delay, lambda: eagle.set_state("idle") if not self.data.any_running() else None)

    def _set_eagle(self, state: str) -> None:
        self.query_one("#eagle", EagleWidget).set_state(state)

    def _status(self, msg: str) -> None:
        if msg:
            self.app.notify(msg, timeout=4)

    def action_doctor(self) -> None:
        self.app.push_screen(DoctorScreen())

    def action_help(self) -> None:
        self.query_one("#monitor", Static).update(_HELP)

    def action_preview(self) -> None:
        """Tab through the selected run's launch-kit artifacts in-app (no file manager needed)."""
        if not self._selected:
            self._status("select a run first, then F4 to preview its results")
            return
        self.app.push_screen(PreviewScreen(self.data, self._selected))

    def action_why_failed(self) -> None:
        """Explain a failed run in plain language: headline + next step + crash log + tail."""
        slug = self._selected or self._last_failed
        if not slug:
            self._status("no run selected")
            return
        detail = self.data.failure_detail(slug)
        if not detail:
            self._status(f"{slug} didn't fail")
            return
        self.app.push_screen(FailureScreen(detail))
