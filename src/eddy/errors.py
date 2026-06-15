"""User-facing error mapping + crash logging.

A stranger should never see a raw ffmpeg/whisper traceback. Known failures map to a plain-language
headline + a concrete next step; anything unexpected still gets a crash log they can attach to a
bug report.
"""

from __future__ import annotations

import os
import platform
import traceback
from pathlib import Path


def friendly_error(e: BaseException) -> tuple[str, str]:
    """(headline, next_step) for a known error type; a generic pair otherwise."""
    from eddy.loop.controller import EditLoopError
    from eddy.media.ffmpeg import FfmpegError
    from eddy.providers.base import ProviderError
    from eddy.runs import SourceError

    msg = str(e)[:300]
    if isinstance(e, SourceError):
        return (f"Input problem: {msg}", "Check the footage path and format, or pass a different file.")
    if isinstance(e, FfmpegError):
        return (f"Media error: {msg}", "Make sure ffmpeg 8+ is installed (run `eddy doctor`) and the file isn't corrupt.")
    if isinstance(e, ProviderError):
        return (f"Editorial brain error: {msg}", "Check your brain with `eddy doctor`, or re-run with --local-only.")
    if isinstance(e, EditLoopError):
        return (f"Couldn't produce a shippable edit: {msg}", "Try a stronger brain (`eddy doctor`) and re-run.")
    return (f"Unexpected {type(e).__name__}: {msg}", "This looks like a bug — please attach the crash log below.")


def crash_dir() -> Path:
    return Path.home() / ".config" / "eddy" / "crashes"


def write_crash_log(e: BaseException, run_dir: Path | None = None) -> Path:
    """Persist a redaction-light crash report (version + platform + traceback) for bug triage.
    Writes into the run dir when one exists, else the user config crashes dir."""
    import eddy

    base = run_dir if (run_dir and Path(run_dir).exists()) else crash_dir()
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"crash-{os.getpid()}.log"
    body = (
        f"eddy {eddy.__version__}\n"
        f"platform: {platform.platform()} python {platform.python_version()}\n"
        f"error: {type(e).__name__}: {e}\n\n"
        + "".join(traceback.format_exception(type(e), e, e.__traceback__))
    )
    path.write_text(body)
    return path
