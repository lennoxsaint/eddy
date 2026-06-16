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


# headline-prefix + concrete next-step, keyed by error CLASS NAME. Keyed by name (not the class
# object) so the TUI can map a failure parsed from a log/receipt — where it only has the class name,
# not a live exception — through the exact same table. friendly_error() uses isinstance (so it still
# catches subclasses); friendly_by_name() is the string-only path.
_FRIENDLY = {
    "SourceError": ("Input problem", "Check the footage path and format, or pass a different file."),
    "FfmpegError": ("Media error", "Make sure ffmpeg 8+ is installed (run `eddy doctor`) and the file isn't corrupt."),
    "ProviderError": ("Editorial brain error", "Check your brain with `eddy doctor`, or re-run with --local-only."),
    "EditLoopError": ("Couldn't produce a shippable edit", "Try a stronger brain (`eddy doctor`) and re-run."),
}


def friendly_by_name(type_name: str, msg: str) -> tuple[str, str]:
    """(headline, next_step) from an error CLASS NAME + message — the string-only path used by the TUI
    when it reconstructs a failure from a log/receipt rather than a live exception."""
    head, nxt = _FRIENDLY.get(
        type_name,
        (f"Unexpected {type_name}", "This looks like a bug — please attach the crash log below."),
    )
    return (f"{head}: {msg[:300]}", nxt)


def friendly_error(e: BaseException) -> tuple[str, str]:
    """(headline, next_step) for a known error type; a generic pair otherwise."""
    from eddy.loop.controller import EditLoopError
    from eddy.media.ffmpeg import FfmpegError
    from eddy.providers.base import ProviderError
    from eddy.runs import SourceError

    for cls in (SourceError, FfmpegError, ProviderError, EditLoopError):
        if isinstance(e, cls):
            return friendly_by_name(cls.__name__, str(e))
    return friendly_by_name(type(e).__name__, str(e))


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
