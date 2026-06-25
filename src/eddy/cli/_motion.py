"""Motion contracts sub-app: update-hyperframes and init-contract commands."""

from __future__ import annotations

from pathlib import Path

import typer

from eddy.cli._app import app

motion_app = typer.Typer(
    name="motion",
    help="HyperFrames-backed motion contracts: pin/cache registry assets and create frame/storyboard proofs.",
    no_args_is_help=True,
)
app.add_typer(motion_app)

DEFAULT_HYPERFRAMES_ROOT = Path.home() / "Developer" / "hyperframes"


@motion_app.command("update-hyperframes")
def motion_update_hyperframes(
    hyperframes_root: Path = typer.Option(
        DEFAULT_HYPERFRAMES_ROOT,
        "--hyperframes-root",
        help="Local HyperFrames checkout to pin and index.",
    ),
    cache_dir: Path = typer.Option(Path(".eddy/hyperframes-cache"), "--cache-dir", help="Where to write the pin/index."),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Pin/index the local HyperFrames checkout. Notify-only; never git-pulls."""
    import json

    from eddy.motion.frame_spec import write_hyperframes_cache

    if not hyperframes_root.exists():
        typer.echo(f"HyperFrames checkout not found: {hyperframes_root}", err=True)
        raise typer.Exit(1)
    res = write_hyperframes_cache(hyperframes_root, cache_dir)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    typer.echo(f"indexed {res['asset_count']} HyperFrames assets at {res['commit'][:12]} -> {cache_dir}")


@motion_app.command("init-contract")
def motion_init_contract(
    project_dir: Path = typer.Argument(..., help="Content/project folder that needs motion artifacts."),
    hyperframes_root: Path = typer.Option(
        DEFAULT_HYPERFRAMES_ROOT,
        "--hyperframes-root",
        help="Local HyperFrames checkout to copy selected references from.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Create frame.md, storyboard.md/html, and a copied HyperFrames asset manifest for a run."""
    import json

    from eddy.motion.frame_spec import build_threadify_motion_contract

    if not hyperframes_root.exists():
        typer.echo(f"HyperFrames checkout not found: {hyperframes_root}", err=True)
        raise typer.Exit(1)
    res = build_threadify_motion_contract(project_dir, hyperframes_root)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    typer.echo(f"frame: {res['frame_spec']}")
    typer.echo(f"storyboard: {res['storyboard']}")
    typer.echo(f"storyboard html: {res['storyboard_html']}")
    typer.echo(f"copied manifest: {res['copied_assets_manifest']}")
