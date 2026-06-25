"""Eddy CLI — drop raw footage in, get a launch kit out.

The root ``app`` lives in :mod:`eddy.cli._app`; every command module below decorates
it with ``@app.command``/``app.add_typer`` as an import side effect, so all of them
must be imported here for the full command set to register on ``app``.
"""

from __future__ import annotations

from eddy.cli._app import app  # import the root FIRST so command modules can bind to it

# Import order mirrors the original module's source order so the root command/sub-app
# registration order — and thus the `eddy --help` listing — is unchanged: setup commands,
# then the four sub-apps (their add_typer side effects), then the pipeline commands.
from eddy.cli import _setup  # noqa: F401
from eddy.cli import _mcp  # noqa: F401
from eddy.cli import _studio_sound  # noqa: F401
from eddy.cli import _motion  # noqa: F401
from eddy.cli import _hooks  # noqa: F401
from eddy.cli import _pipeline  # noqa: F401

__all__ = ["app"]
