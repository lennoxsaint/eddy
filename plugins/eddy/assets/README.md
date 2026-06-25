# Eddy Plugin Assets

This folder contains the Codex plugin card imagery used by Eddy.

- `eddy-eagle-icon.png`: transparent 8-bit eagle composer icon.
- `eddy-eagle-logo.png`: square logo for larger plugin surfaces.

Regenerate both files from the terminal UI sprite source with:

```bash
.venv/bin/python scripts/generate_plugin_assets.py
```

Eddy intentionally ships without remote asset dependencies so the plugin can install from Git and
run locally.
