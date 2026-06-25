"""Eddy MCP server sub-app: serve and install commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from eddy.cli._app import app

mcp_app = typer.Typer(name="mcp", help="Eddy MCP server: serve it over stdio, or install it into a client.", no_args_is_help=True)
app.add_typer(mcp_app)


@mcp_app.command("serve")
def mcp_serve() -> None:
    """Run the Eddy MCP server over stdio (what a client launches; not for interactive use)."""
    from eddy.mcp_server.server import main

    main()


@mcp_app.command("install")
def mcp_install(
    client: str = typer.Option(..., "--client", help="claude-desktop | claude-code | codex."),
    command: str = typer.Option("eddy-mcp", "--command", help="The server command the client should launch."),
    path: Optional[Path] = typer.Option(None, "--path", help="Override the client's config path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be written, change nothing."),
) -> None:
    """Register the Eddy MCP server with a client (idempotent; backs up + merges, never clobbers)."""
    from eddy.mcp_server.install import CLIENTS, install

    if client not in CLIENTS:
        typer.echo(f"✗ unknown client {client!r}; choose one of {', '.join(CLIENTS)}", err=True)
        raise typer.Exit(1)
    res = install(client, command=command, path=path, dry_run=dry_run)
    from eddy.ui import console as ui

    if dry_run:
        ui.note(f"would write {res['path']}:")
        ui.console().print(res["content_preview"])
        if res.get("existing_config_preserved"):
            ui.note("existing config detected; dry-run preview is limited to the Eddy stanza")
        return
    ui.ok(f"{res['action']} {res['path']} — mcpServers.eddy → {command}")
    if res.get("backup"):
        ui.note(f"backup: {res['backup']}")
