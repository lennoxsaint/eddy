# Eddy MCP server

`eddy-mcp` exposes every Eddy capability as [Model Context Protocol](https://modelcontextprotocol.io)
tools, so **Claude Code**, **Codex**, and **Claude Desktop** can drive Eddy — start an edit, watch it,
and read the launch kit — as a tool, with no copy-paste.

Install the server (it's an optional extra so the base install stays slim):

```bash
pipx install "eddy[mcp] @ git+https://github.com/lennoxsaint/eddy.git@v1.8.1"
```

That puts `eddy-mcp` on your PATH. It speaks MCP over **stdio** — clients launch it; you never run it
by hand.

## How it works (the job model)

A full edit takes 5–15 minutes, so long operations are **asynchronous jobs**:

1. `eddy_run_start(source, …)` → returns a `job_id` immediately (the run slug).
2. `eddy_job_status(job_id)` → `running | completed | failed | interrupted` + the current `phase`.
3. `eddy_artifacts(run)` → titles, description, chapters, shorts ledger, final video path.

Each long op runs as its own `eddy` subprocess, so a run's own offline/egress state is isolated and
the hardened CLI path is reused. Cheap reads (`eddy_runs`, `eddy_run_inspect`, `eddy_doctor`,
`eddy_profiles`, `eddy_qa`, `eddy_pick`, `eddy_artifacts`) return instantly. Destructive tools
(`eddy_clean`, `eddy_purge`) refuse without `confirm=true`. Eddy never publishes or uploads.

## Install into a client

The installer is idempotent, backs the existing config up (`*.eddybak`), and merges **only** the
`eddy` entry — it never clobbers your other servers or settings:

```bash
eddy mcp install --client claude-desktop
eddy mcp install --client claude-code     # writes ./.mcp.json (project scope)
eddy mcp install --client codex           # ~/.codex/config.toml
eddy mcp install --client codex --dry-run # preview, change nothing
```

### Or paste it in by hand

**Claude Desktop** — `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "eddy": { "command": "eddy-mcp", "args": [] }
  }
}
```

**Claude Code** — project `.mcp.json` (or `claude mcp add eddy -- eddy-mcp`):

```json
{
  "mcpServers": {
    "eddy": { "command": "eddy-mcp", "args": [] }
  }
}
```

**Codex** — `~/.codex/config.toml`:

```toml
[mcp_servers.eddy]
command = "eddy-mcp"
args = []
```

## Claude Code plugin

For Claude Code there's a one-shot plugin at [`integrations/claude-code/`](../integrations/claude-code)
that bundles the MCP server with slash commands and a skill:

- `/eddy-run <footage>` — start a full edit and report the launch kit
- `/eddy-shorts <footage>` — mine vertical shorts only
- `/eddy-status [run]` — recent runs + in-flight jobs
- an **eddy** skill that teaches the agent the start→poll→read job model

Install it by pointing Claude Code at the plugin directory (see its
[README](../integrations/claude-code/README.md)). Publishing to a marketplace is a separate,
owner-gated step.

## Tools

| Read (instant) | Jobs (start → poll → read) | Destructive (confirm=true) |
|---|---|---|
| `eddy_doctor` | `eddy_run_start` | `eddy_clean` |
| `eddy_runs` | `eddy_shorts_start` | `eddy_purge` |
| `eddy_run_inspect` | `eddy_transcribe_start` | |
| `eddy_profiles` | `eddy_render_start` | |
| `eddy_qa` | `eddy_batch_start` | |
| `eddy_pick` | `eddy_job_status` | |
| `eddy_artifacts` | `eddy_job_cancel` / `eddy_jobs` | |

## Air-gapped installs

`mcp` is an **optional extra**, so a base `eddy` install is unchanged. Adding `[mcp]` pulls the MCP
SDK and its deps (`anyio`, `sse-starlette`, `pydantic-settings`, `starlette`, `uvicorn`, …). When
building an offline wheelhouse (`scripts/build_wheelhouse.sh`), include the extra so those wheels are
staged:

```bash
python -m pip download ".[mcp]" --only-binary=:all: -d wheelhouse
```

See [`AIRGAP.md`](AIRGAP.md) for the full offline story.
