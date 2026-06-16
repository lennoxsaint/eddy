"""Eddy's face: the terminal brand layer.

A thin presentation package — sprite art, the EDDY wordmark, a Rich console wrapper, and the
animator — kept separate from logic so the rest of the codebase stays dumb about styling and every
human-facing surface shares one look. Nothing here touches the network, disk, or editorial state.
"""

from __future__ import annotations
