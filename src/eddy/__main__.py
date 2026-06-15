"""Enable `python -m eddy` (path-agnostic; used by the CI wheel smoke)."""

from eddy.cli import app

app()
