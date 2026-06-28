# Eddy in Codex

Recommended Codex install shape: **plugin first, skill plus MCP fallback**.

The public one-sentence install prompt is:

> @plugin-creator install [lennoxsaint/eddy](https://github.com/lennoxsaint/eddy)

That is the prompt Codex users should paste into the Plugin Creator flow. Do not publish a
machine-specific skill path as the public install prompt; local absolute paths are maintainer
convenience only.

## What the plugin installs

The shipped Codex plugin lives at:

```text
plugins/eddy/
```

It contains:

- `.codex-plugin/plugin.json` — Codex plugin metadata and starter prompts.
- `skills/eddy/SKILL.md` — the editing contract the agent reads when `@Eddy` is mentioned.
- `.mcp.json` — the plugin MCP server config.
- `scripts/eddy_plugin_mcp.py` — launches the managed Eddy MCP server.
- `scripts/eddy_plugin_bootstrap.py` — installs and updates the active Eddy engine from stable tags.

The plugin skill is intentionally thin. It does not freeze editing behavior at plugin-install time.
On install and on first use, the plugin wrapper checks the latest stable `vX.Y.Z` GitHub tag, installs
that tag into `~/.eddy/source` and `~/.eddy/venv`, smoke-checks it, and only then swaps it active. If
the update fails, it keeps the previous working tag and writes the exact blocker to
`~/.eddy/plugin-state.json`.

Automatic updates track the latest stable tag, not `main`.

## Marketplace entry

The repo ships a marketplace entry at:

```text
.agents/plugins/marketplace.json
```

It points at the plugin subdirectory:

```json
{
  "name": "eddy",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/lennoxsaint/eddy.git",
    "path": "./plugins/eddy",
    "ref": "v1.10.4"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Creativity"
}
```

Preview or update a personal marketplace file with:

```bash
python3 scripts/install_codex_plugin.py --dry-run --json
python3 scripts/install_codex_plugin.py
```

The installer writes `~/.agents/plugins/marketplace.json` by default and emits Codex plugin
deeplinks for local review.

## Use after install

Once installed, the user can attach footage and mention Eddy:

> @Eddy

If raw video files are attached and no instruction text is supplied, Eddy defaults to:

```text
eddy_edit_options(source=<attached path or folder>, format="youtube")
```

If more than one runnable path exists, the agent asks, "How do you want this edited?" and shows plain
English options with benefits, drawbacks, privacy/cost notes, and a recommendation. If only one path
is runnable, the agent starts it directly:

```text
eddy_edit_start(source=<attached path or folder>, format="youtube", edit_path=<selected_option_id>)
```

That means proof-gated long-form YouTube edit plus Shorts and launch packaging when the relevant gates pass. If
Codex cannot resolve an attachment into a filesystem path, Eddy reports
`attached_source_unresolved` with a paste-ready retry instruction instead of guessing.

## Shorts defaults

- Separate camera + screen sources: Yassy stacked layout — square camera top, one-line karaoke
  captions in the middle, screen/proof panel bottom.
- Single talking-head video source: `talking_head_916` — crop/fill to 1080x1920, face centered,
  blinkless segment assembly, one-line karaoke captions in the bottom third.
- Audio-only or ambiguous multi-file inputs: fail loudly with exact blockers.

## Skill plus MCP fallback

For older Codex clients, local development, or Claude-style installs, the fallback remains:

```bash
python3 scripts/install_codex.py
```

That command:

1. links/copies Eddy into `~/.codex/skills/eddy`;
2. installs Eddy from the checkout with the MCP extra;
3. provisions Eddy's local Studio Sound backend unless explicitly skipped;
4. writes a stable MCP wrapper at `~/.eddy/bin/eddy-mcp`;
5. registers the MCP server in `~/.codex/config.toml`;
6. runs verification commands and reports exact blockers.

Preview it safely:

```bash
python3 scripts/install_codex.py --dry-run --json
```

## Why plugin first?

A plugin is the clean Codex distribution unit because it bundles the skill and MCP config together.
MCP alone gives tools, but it does not teach the agent Eddy's editorial contract. A skill alone can
teach the contract, but long video edits are better as start/poll/read jobs. The plugin ships both.

Eddy still does not upload, publish, send, schedule, or mutate source media.
