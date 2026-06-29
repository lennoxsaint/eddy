# Eddy — Claude Code plugin

Drive [Eddy](../../README.md), a local-first agentic video editor, from Claude Code. This plugin
bundles the `eddy-mcp` server with slash commands and a skill.

## What's inside

- **`.mcp.json`** — registers the `eddy-mcp` server.
- **Commands** — `/eddy-run <footage>`, `/eddy-shorts <footage>`, `/eddy-status [run]`.
- **Skill** — `eddy`, which teaches the agent the start→poll→read job model.
- **`hooks/`** — a placeholder hooks slot (no active hooks by default).

## Prerequisites

```bash
pipx install "eddy[mcp] @ git+https://github.com/lennoxsaint/eddy.git@v1.10.5"
```

## Install

Point Claude Code at this directory as a plugin (local install), e.g. add it to your
`~/.claude/plugins` or load it via your plugin config, then restart Claude Code. Verify with:

```
/eddy-status
```

If you only want the MCP server (no commands/skill), run `eddy mcp install --client claude-code`
instead, which writes a project `.mcp.json`.

## Use

```
/eddy-run ~/footage/2026-06-15-lesson
/eddy-shorts ~/footage/podcast.mp4
/eddy-status
```

`/eddy-run` should call `eddy_edit_options` first, then `eddy_edit_start` with the selected path. Eddy produces local files only — it
never publishes or uploads. Destructive tools require `confirm=true`. Publishing this plugin to a
marketplace is a separate, owner-gated step.
