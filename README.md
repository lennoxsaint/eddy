# Eddy

**Drop raw footage in. Get a complete YouTube launch kit out.**

Eddy is a local-first agentic video editor. You record like a human — retakes, false starts,
long gaps, messy texture — and Eddy loops a local model over the footage (transcript → cut plan →
simulation → proxy render → QA → judge) until the edit is actually done, then packages the launch:

- edited long video (publish-ready)
- shorts with karaoke captions in your approved layout
- thumbnail candidates
- 10 grounded title candidates
- chapters + YouTube description

Editing is **free and unlimited** by default: the editorial brain runs on your own hardware via
Ollama. Weaker machine? `eddy doctor` detects your hardware and recommends a cloud brain instead —
Anthropic/OpenAI APIs, or your existing ChatGPT/Claude subscription via the `codex`/`claude` CLIs.

Your raw video and audio never leave your machine, nothing is ever published, and sources are
never modified (hash-verified). By default (`editorial='auto'`) the editorial brain uses the
strongest brain available — if you have a `claude`/`codex` CLI or an API key, your **transcript
text** is sent to that provider; the optional thumbnail step uploads selected face frames to an
image API. Run with `--local-only` (or `EDDY_OFFLINE=1`) to keep everything fully on-device. See
[PRIVACY.md](PRIVACY.md) for the exact per-tier data flow. Every model call is written to receipts
you can audit.

## Quickstart

```bash
pipx install /path/to/eddy        # or: pip install -e .
eddy doctor                        # detects hardware, recommends a brain, writes config
eddy run path/to/footage/          # camera.mp4 [+ screen.mp4 + mic.wav], or one composite .mp4
```

Watch progress: `eddy status <run>`. Everything lands in `~/.eddy/runs/<date-slug>/final/launch-kit/`
(configurable via `paths.runs_dir`). Reclaim scratch afterwards with `eddy clean <run>`.
(Pre-0.6 runs lived under `~/Eddy/runs`; move them if you want them under the new default.)

Stage-by-stage instead: `eddy transcribe`, `eddy plan`, `eddy render`, `eddy shorts`, `eddy package`.

Bare `eddy` wakes the mascot — **Eddy the eagle** — a branded splash with your recent runs and
next steps. Preview it anytime with `eddy mascot` (`--state`, `--animate`). Colour is automatic on a
real terminal and off when piped; set `NO_COLOR=1` or `EDDY_NO_ANIM=1` to tone it down.

## Drive Eddy from Claude Code, Codex, or Claude Desktop

Eddy ships an MCP server so an agent can start edits, watch them, and read the launch kit as tools:

```bash
pipx install 'eddy[mcp]'                 # adds the eddy-mcp server
eddy mcp install --client claude-desktop # or claude-code | codex (idempotent, backs up, merges)
```

A full edit is a job: `eddy_run_start` returns a `job_id`, `eddy_job_status` polls it, `eddy_artifacts`
reads the result. There's also a one-shot Claude Code plugin (`/eddy-run`, `/eddy-shorts`,
`/eddy-status` + a skill) at [`integrations/claude-code/`](integrations/claude-code). Full details in
[docs/MCP.md](docs/MCP.md).

## Requirements

- ffmpeg 8+
- Python 3.11+
- A brain: [Ollama](https://ollama.com) with a ~27B model (best on 32GB+ unified memory),
  or any of: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `codex` CLI, `claude` CLI.
- Optional, thumbnails only: `GEMINI_API_KEY` / `OPENAI_API_KEY` (skipped gracefully if absent).

## Status

v0.1 — building. Board: Linear team EDD / project "Eddy v1". Product contract: `docs/PRD.md`.
Origin story and decisions: `docs/decision-log.md`.

## For agents

Read `AGENTS.md` first. Hard gates live there.
