# Eddy in Codex

Recommended Codex install shape: **skill plus MCP**.

That means:

- the **skill** tells Codex when and how to use Eddy;
- the **MCP server** gives Codex actual tools to start an edit, poll the job, and read artifacts;
- a **plugin** is not the Codex Club path today unless Eddy is packaged into Codex's curated plugin
  directory later.

OpenAI describes Codex plugins as bundles that can package skills, app integrations, and MCP server
configuration. That is the polished distribution target. For sharing Eddy from a public GitHub repo
right now, the reliable path is a repo-local installer that registers the skill plus MCP.

## One sentence for a user

Give Codex the repo link and say:

> Install https://github.com/lennoxsaint/eddy into Codex, then use Eddy to edit my attached footage.

Codex should clone the repo, read `SKILL.md`, and run:

```bash
python3 scripts/install_codex.py
```

That command:

1. symlinks Eddy into `~/.codex/skills/eddy`;
2. installs Eddy from the checkout with the MCP extra, preferring Python 3.12/3.11 for video and
   audio wheel compatibility;
3. provisions Eddy's local Studio Sound backend unless explicitly skipped;
4. writes a stable MCP wrapper at `~/.eddy/bin/eddy-mcp`;
5. registers the MCP server in `~/.codex/config.toml`;
6. runs basic verification commands and reports exact blockers.

Preview it safely:

```bash
python3 scripts/install_codex.py --dry-run --json
```

## Why not just MCP?

MCP alone gives tools, but it does not teach the agent Eddy's editorial contract: immutable sources,
Studio Sound gates, Shorts quality gates, motion proof, no publishing, no blur by default, and exact
blocker reporting. That belongs in a skill.

## Why not just a skill?

A skill alone can tell Codex to run shell commands, but long video edits are better as fire-and-poll
jobs. MCP gives Codex `eddy_edit_start`, `eddy_job_status`, and `eddy_artifacts`, so the agent can keep
moving without treating a 20-minute render as one giant brittle shell command.

## Why not a plugin?

A plugin is the cleanest future packaging format because it can bundle the skill and MCP config
together. It is not the Codex Club path today because Eddy is being shared from a public GitHub repo,
not from a curated Codex plugin directory. Until Eddy is packaged and approved as a Codex plugin, use
skill plus MCP.

## What “installed” means

A successful Codex install has all of these:

- `~/.codex/skills/eddy` exists and points at, or copies, the Eddy repo.
- `eddy` imports from the installed checkout.
- `~/.eddy/bin/eddy-mcp` exists and launches `python -m eddy.mcp_server.server`.
- `~/.codex/config.toml` contains:

```toml
[mcp_servers.eddy]
command = "/Users/<user>/.eddy/bin/eddy-mcp"
args = []
```

- `eddy bootstrap --json` is ready or gives exact repair steps.
- `eddy studio-sound doctor` is green before a final production edit is accepted.

## Use after install

Once installed, the user can say:

> Use Eddy to edit this footage.

Codex should use the `eddy_edit_start` MCP tool when available. If MCP tools are not visible yet,
Codex should run:

```bash
eddy edit /path/to/footage-or-folder
```

The correct output is either a local launch kit or an exact blocker with a repair plan. Eddy still
does not upload, publish, send, or schedule anything.
