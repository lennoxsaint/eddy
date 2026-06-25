"""Hooks playbook sub-app: status and corpus-build commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from eddy.cli._app import app

hooks_app = typer.Typer(
    name="hooks",
    help="Build and validate Eddy's offline short-form hook playbook.",
    no_args_is_help=True,
)
app.add_typer(hooks_app)


@hooks_app.command("status")
def hooks_status(
    playbook: Path = typer.Option(Path("docs/references/short-form-hook-playbook.jsonl"), "--playbook"),
    min_records: int = typer.Option(1000, "--min-records"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Validate the baked offline short-form hook playbook."""
    import json

    from eddy.hooks.playbook import playbook_status

    res = playbook_status(playbook, min_records=min_records)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    if res["ready"]:
        typer.echo(f"hook playbook ready: {res['valid_count']}/{res['required_count']} valid hooks")
    else:
        typer.echo(f"{res['blocker']}: {res['valid_count']}/{res['required_count']} valid hooks at {playbook}", err=True)
        raise typer.Exit(1)


@hooks_app.command("build-supadata")
def hooks_build_supadata(
    urls_file: Path = typer.Argument(..., help="Text file with one public short-form URL per line."),
    out: Path = typer.Option(Path("docs/references/short-form-hook-playbook.jsonl"), "--out"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Build the hook corpus once from supplied public URLs via Supadata."""
    import json

    from eddy.hooks.playbook import build_from_supadata

    urls = [line.strip() for line in urls_file.read_text().splitlines() if line.strip() and not line.startswith("#")]
    res = build_from_supadata(urls, out)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    typer.echo(f"wrote {res['valid_count']} valid hooks -> {out}")
    if not res["ready"]:
        typer.echo(f"{res['blocker']}: collect more proven public URLs and rerun", err=True)
        raise typer.Exit(1)


@hooks_app.command("build-youtube-metadata")
def hooks_build_youtube_metadata(
    out: Path = typer.Option(Path("docs/references/short-form-hook-playbook.jsonl"), "--out"),
    queries_file: Optional[Path] = typer.Option(None, "--queries-file", help="Optional newline-delimited ytsearch queries."),
    target_records: int = typer.Option(1000, "--target-records"),
    per_query: int = typer.Option(80, "--per-query"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Build the offline corpus from public YouTube metadata without downloading media/transcripts."""
    import json

    from eddy.hooks.playbook import build_from_youtube_metadata

    queries = None
    if queries_file:
        queries = [line.strip() for line in queries_file.read_text().splitlines() if line.strip() and not line.startswith("#")]
    res = build_from_youtube_metadata(out, queries=queries, target_records=target_records, per_query=per_query)
    if json_out:
        typer.echo(json.dumps(res, indent=2))
        return
    typer.echo(f"wrote {res['valid_count']} valid metadata hooks -> {out}")
    if not res["ready"]:
        typer.echo(f"{res['blocker']}: add more public queries or use Supadata URLs", err=True)
        raise typer.Exit(1)
