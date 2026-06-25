"""One tiny logger so best-effort failures are diagnosable without changing behavior.

Eddy's audit trail is ``receipts.jsonl`` (per run). But a lot of best-effort code runs with no run
context — capability probes, the wake splash, hardware detection — and historically swallowed
failures with a bare ``except Exception: pass``, leaving nothing to debug when a probe silently
returned empty. This logger fills that gap:

* **Silent by default.** With no env var set it attaches a ``NullHandler`` and emits nothing, so
  normal runs, the TUI, and machine-readable stdout ledgers stay clean.
* **Opt-in surfacing.** Set ``EDDY_DEBUG=1`` (or ``EDDY_LOG=debug|info|warning``) to surface those
  swallowed reasons on **stderr** — never stdout, so JSON output stays parseable.
* **Never raises.** ``debug()`` swallows its own errors; logging diagnostics must never break a run.
"""

from __future__ import annotations

import logging
import os

_NAME = "eddy"
_configured = False


def _configure(log: logging.Logger) -> None:
    global _configured
    _configured = True
    # Start from a clean slate so reconfiguration never stacks handlers (and so a handler attached by
    # an outer harness — e.g. pytest's log capture — doesn't leak into our silent-by-default contract).
    for handler in list(log.handlers):
        log.removeHandler(handler)
    level = os.environ.get("EDDY_LOG", "").strip().upper()
    if not level and os.environ.get("EDDY_DEBUG"):
        level = "DEBUG"
    if level:
        handler = logging.StreamHandler()  # stderr by default — keeps stdout ledgers clean
        handler.setFormatter(logging.Formatter("eddy %(levelname)s %(name)s: %(message)s"))
        log.addHandler(handler)
        log.setLevel(getattr(logging, level, logging.INFO))
    else:
        log.addHandler(logging.NullHandler())
        log.setLevel(logging.WARNING)
    log.propagate = False


def logger() -> logging.Logger:
    """The shared ``eddy`` logger, configured once from the environment."""
    log = logging.getLogger(_NAME)
    if not _configured:
        _configure(log)
    return log


def debug(msg: str, *args: object) -> None:
    """Best-effort debug line for a swallowed failure. Never raises; ``%s``-style lazy formatting."""
    try:
        logger().debug(msg, *args)
    except Exception:
        pass
