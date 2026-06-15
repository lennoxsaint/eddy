"""Offline / local-only enforcement.

The product promise is "nothing leaves your machine" — but by default the editorial brain
resolves to a cloud model (`editorial='auto'`) and Whisper will download weights from HuggingFace.
This module is the single switch that makes the promise literally true: `--local-only` (CLI) or
`EDDY_OFFLINE=1` (env) forces the editorial brain to the local provider, makes Whisper use only
already-downloaded weights, and skips the cloud thumbnail path.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}


def is_offline() -> bool:
    """True when the run must stay fully on-device (set by --local-only or EDDY_OFFLINE)."""
    return os.environ.get("EDDY_OFFLINE", "").strip().lower() in _TRUE


def set_offline(value: bool = True) -> None:
    """Used by the --local-only CLI flag so all downstream code sees one consistent signal."""
    os.environ["EDDY_OFFLINE"] = "1" if value else ""
