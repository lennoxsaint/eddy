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

Nothing is ever uploaded or published. Sources are never modified (hash-verified). Every decision
the agent makes is written to receipts you can audit.

## Quickstart

```bash
pipx install /path/to/eddy        # or: pip install -e .
eddy doctor                        # detects hardware, recommends a brain, writes config
eddy run path/to/footage/          # camera.mp4 [+ screen.mp4 + mic.wav], or one composite .mp4
```

Watch progress: `eddy status <run>`. Everything lands in `runs/<date-slug>/final/launch-kit/`.

Stage-by-stage instead: `eddy transcribe`, `eddy plan`, `eddy render`, `eddy shorts`, `eddy package`.

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
