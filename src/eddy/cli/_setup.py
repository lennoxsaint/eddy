"""Top-level setup commands: doctor, bootstrap, update-check, mascot, tui."""

from __future__ import annotations

from typing import Optional

import typer

from eddy.cli._app import _recent_runs, app


@app.command()
def tui() -> None:
    """Open the full-screen Eddy TUI (runs list, live monitor, command/NL input)."""
    from eddy.tui.app import run_tui

    run_tui()


@app.command()
def doctor(
    ping: bool = typer.Option(False, "--ping", help="Round-trip the active provider, incl. JSON-schema output."),
    all_providers: bool = typer.Option(False, "--all", help="Ping every configured provider."),
    write: bool = typer.Option(True, help="Write recommendations into config."),
) -> None:
    """Detect hardware + brains, recommend a provider tier, write config."""
    from eddy.doctor import run_doctor

    run_doctor(ping=ping, all_providers=all_providers, write=write)


@app.command()
def bootstrap(
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show the exact repair plan needed before Eddy can edit reliably."""
    import json

    from eddy.bootstrap import repair_plan
    from eddy.doctor import preflight

    checks = preflight()
    plan = repair_plan(checks)
    out = {"preflight": checks, "repair_plan": plan}
    if json_out:
        typer.echo(json.dumps(out, indent=2))
        raise typer.Exit(0 if plan["status"] == "ready" else 1)
    for check in checks:
        mark = "ok  " if check["ok"] else "FAIL"
        typer.echo(f"{check['check']:13} {mark} {check['detail']}")
    if plan["status"] == "ready":
        typer.echo("\nbootstrap: ready")
        return
    typer.echo("\nbootstrap: repair needed")
    for action in plan["actions"]:
        typer.echo(f"  - {action['id']}: {action['title']}")
        if action.get("command"):
            typer.echo(f"    command: {action['command']}")
        typer.echo(f"    why: {action['reason']}")
    raise typer.Exit(1)


@app.command("update-check")
def update_check(
    remote: str = typer.Option("origin", "--remote", help="Git remote to compare against."),
    branch: str = typer.Option("main", "--branch", help="Remote branch to compare against."),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Check whether this Eddy checkout has updates. Notify-only; never pulls."""
    import json

    from eddy.update_check import check_for_update

    result = check_for_update(remote=remote, branch=branch)
    if json_out:
        typer.echo(json.dumps(result, indent=2))
        return
    status = result.get("status", "unknown")
    if result.get("ok") and status == "update_available":
        typer.echo(f"update available: {result['local_sha'][:8]} -> {result['remote_sha'][:8]}")
        typer.echo(result["next_action"])
    elif result.get("ok"):
        typer.echo(f"up to date: {result.get('local_sha', '')[:8]}")
    else:
        typer.echo(f"update check failed: {status} ({result.get('error', 'no detail')})", err=True)
        raise typer.Exit(1)


@app.command()
def mascot(
    state: Optional[str] = typer.Option(None, "--state", help="idle | thinking | working | success | error."),
    small: bool = typer.Option(False, "--small", help="Show the compact eagle instead of the hero size."),
    animate: bool = typer.Option(False, "--animate", help="Run a short animation demo (interactive terminals)."),
) -> None:
    """Preview Eddy the eagle: the wake screen, a single sprite state, or a short animation demo."""
    from eddy.ui import console as ui

    if animate:
        import time

        from eddy.ui.animate import animate as run_anim

        with run_anim(status="[eddy.accent]editing…[/eddy.accent] cut 3/6 · q0.82", state="working", final_state="success") as h:
            time.sleep(1.8)
            h.update(status="[eddy.accent]rendering final…[/eddy.accent]")
            time.sleep(1.4)
        ui.ok("done · launch kit ready")
        return
    if state:
        ui.print_sprite(state, small=small)
        return
    ui.console().print(ui.wake_screen(runs=_recent_runs()))
