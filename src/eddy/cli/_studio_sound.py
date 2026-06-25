"""Studio Sound sub-app: doctor and install commands."""

from __future__ import annotations

import typer

from eddy.cli._app import app

studio_sound_app = typer.Typer(
    name="studio-sound",
    help="Install or inspect Eddy's heavy local Studio Sound backend.",
    no_args_is_help=True,
)
app.add_typer(studio_sound_app)


@studio_sound_app.command("doctor")
def studio_sound_doctor(json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON.")) -> None:
    """Check whether the local Studio Sound quality backend is installed."""
    import json

    from eddy.studio_sound_env import status

    res = status()
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    mark = "OK " if res["quality_ready"] else "FAIL"
    typer.echo(f"studio sound {mark} {res.get('deep_filter') or 'missing DeepFilterNet backend'}")
    if not res["quality_ready"]:
        typer.echo("next: eddy studio-sound install")


@studio_sound_app.command("install")
def studio_sound_install(
    force: bool = typer.Option(False, "--force", help="Recreate the Studio Sound env before installing."),
    include_resemble: bool = typer.Option(False, "--include-resemble", help="Also try the optional Resemble Enhance backend."),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Provision Eddy's default heavy local Studio Sound backend."""
    import json

    from eddy.studio_sound_env import install_studio_sound

    res = install_studio_sound(force=force, include_resemble=include_resemble)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
    elif res.get("ok"):
        typer.echo(f"studio sound OK — {res['status'].get('deep_filter')}")
    else:
        typer.echo(f"studio sound FAIL at {res.get('stage')}: {res.get('error')}", err=True)
        typer.echo(f"next: {res.get('next_action', 'fix the dependency error and rerun')}", err=True)
    if not res.get("ok"):
        raise typer.Exit(1)
