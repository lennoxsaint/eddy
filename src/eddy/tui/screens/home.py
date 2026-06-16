"""The Eddy home screen: animated eaglet header, a runs list, a live run monitor, and a bottom input
bar that takes Eddy commands, /slash commands, or plain-language requests (interpreted by the local
brain, always confirmed). A 2s poll keeps the runs list + monitor + the eaglet's mood live."""

from __future__ import annotations

from textual import on, work
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Static

from eddy.tui.intents import Intent, interpret_nl, parse_command
from eddy.tui.runner import TuiData
from eddy.tui.screens.confirm import ConfirmScreen
from eddy.tui.screens.doctor import DoctorScreen
from eddy.tui.widgets.eagle import EagleWidget

_GOLD = "#f5b836"
_DIM = "#8b909b"

_HELP = (
    f"[{_GOLD} bold]Eddy[/] — type a command, a /slash, or just ask:\n\n"
    "  run <footage> [minutes]   start a full edit\n"
    "  shorts <footage>          mine vertical shorts\n"
    "  render <run>              re-render a run\n"
    "  open <run>                show a run's results\n"
    "  clean <run> / purge <run> reclaim / delete (confirmed)\n"
    "  doctor · runs · /help · /quit\n\n"
    f"[{_DIM}]…or 'edit my podcast and keep it punchy' — the local brain interprets it (you confirm).[/]\n"
    f"[{_DIM}]ctrl+d doctor · ctrl+r refresh · ctrl+c quit[/]"
)


class HomeScreen(Screen):
    BINDINGS = [
        ("ctrl+r", "refresh", "Refresh"),
        ("ctrl+d", "doctor", "Doctor"),
        ("f1", "help", "Help"),
    ]

    def __init__(self, data: TuiData) -> None:
        super().__init__()
        self.data = data
        self._selected: str | None = None
        self._was_running = False

    def compose(self):
        with Horizontal(id="hdr"):
            yield EagleWidget(small=True, id="eagle")
            yield Static(id="title")
        with Horizontal(id="main"):
            yield DataTable(id="runs", cursor_type="row")
            yield VerticalScroll(Static(_HELP, id="monitor"), id="monitorwrap")
        yield Input(placeholder="run <footage> · doctor · /help · or just ask…", id="cmd")
        yield Footer()

    def on_mount(self) -> None:
        from eddy import __version__

        self.query_one("#title", Static).update(
            f"[{_GOLD} bold]EDDY[/]\n[{_DIM}]local-first agentic video editor[/]\n"
            f"[{_DIM}]brain: {self.data.brain_label()} · v{__version__}[/]"
        )
        table = self.query_one("#runs", DataTable)
        table.add_columns("run", "phase")
        self._refresh_table()
        self.set_interval(2.0, self._poll)
        self.query_one("#cmd", Input).focus()

    # --- runs list ---------------------------------------------------------------------------------
    def _refresh_table(self) -> None:
        table = self.query_one("#runs", DataTable)
        prev = self._selected
        table.clear()
        for r in self.data.runs():
            table.add_row(r["slug"], r.get("phase", "?"), key=r["slug"])
        if prev and prev in [r["slug"] for r in self.data.runs()]:
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
        lines = [f"[{_GOLD} bold]{slug}[/]", f"phase: {st.get('phase', '?')}"]
        attempts = st.get("attempts") or []
        if attempts:
            a = attempts[-1]
            lines.append(
                f"iter {a.get('iteration', '?')} · q{a.get('quality', 0):.2f} · judge {a.get('judge_score', 0):.1f}"
                f" · gates {'✓' if a.get('gates_passed') else '✗'}"
            )
        if st.get("best_iter") is not None:
            lines.append(f"best: iteration {st['best_iter']}")
        if d["artifacts"]:
            lines.append("")
            lines.append(f"[{_DIM}]final/:[/] {', '.join(d['artifacts'][:12])}")
        titles = self.data.artifact_text(slug, "titles.md")
        if titles:
            lines.append("")
            lines.append(f"[{_DIM}]titles:[/]\n{titles[:600]}")
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
        provider = None
        try:
            from eddy.config import load_config
            from eddy.providers.base import get_provider

            provider = get_provider(load_config())
        except Exception:
            provider = None
        intent = interpret_nl(text, provider)
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
            return
        if intent.needs_confirm:
            self.app.push_screen(ConfirmScreen(intent.describe()), lambda ok: self._maybe_exec(ok, intent))
        else:
            self._exec(intent)

    def _maybe_exec(self, ok: bool | None, intent: Intent) -> None:
        if ok:
            self._exec(intent)
        else:
            self._status("cancelled")

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
            eagle.set_state("success")
            self.set_timer(3.0, lambda: eagle.set_state("idle") if not self.data.any_running() else None)
        if self._selected:
            self._update_monitor(self._selected)

    def _set_eagle(self, state: str) -> None:
        self.query_one("#eagle", EagleWidget).set_state(state)

    def _status(self, msg: str) -> None:
        if msg:
            self.app.notify(msg, timeout=4)

    def action_doctor(self) -> None:
        self.app.push_screen(DoctorScreen())

    def action_help(self) -> None:
        self.query_one("#monitor", Static).update(_HELP)
