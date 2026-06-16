"""Eddy's full-screen terminal app (Textual).

Bare `eddy` on an interactive terminal opens this TUI: an animated chibi-eaglet header, a runs list, a
live run monitor, and a bottom input bar that takes Eddy commands, slash-commands, OR plain-language
requests (interpreted by the local brain, always confirmed before acting). Piped / non-TTY / `--no-tui`
falls back to the printed banner, so CI, pipes, and the MCP subprocess are unaffected.
"""

from __future__ import annotations
