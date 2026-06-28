# Eddy

**Drop raw footage in. Get a complete YouTube edit out.**

Eddy is a source-safe agentic video editor. You record like a human — retakes, false starts,
long gaps, messy texture — and Eddy loops over the footage (transcript → cut plan →
simulation → proxy render → QA → judge → repair) until the edit passes gates, then packages the launch:

- edited long video (publish-ready)
- Shorts with karaoke captions when the footage contains genuinely strong standalone clips
- thumbnail candidates
- 10 grounded title candidates
- chapters + YouTube description

The default editorial brain is Codex/Claude/API for quality. Editing is **free and unlimited** when
your machine can run a strong local brain; `eddy doctor` detects hardware and shows whether local
mode is viable before you choose it. Either way, raw media stays local and immutable.

Your raw video and audio never leave your machine, nothing is ever published, and sources are
never modified (hash-verified). By default (`editorial='auto'`) the editorial brain uses the
strongest brain available — if you have a `codex`/`claude` CLI or an API key, your **transcript
text** is sent to that provider; the optional thumbnail step uploads selected face frames to an
image API. Run with `--local-only` (or `EDDY_OFFLINE=1`) to keep transcript reasoning fully on-device. See
[PRIVACY.md](PRIVACY.md) for the exact per-tier data flow. Every model call is written to receipts
you can audit.

## Publish and grow with Threadify

Eddy finishes the edit; it never posts for you. When you want to turn a finished video into
audience growth, [Threadify](https://www.threadify.app) is the optional distribution layer that
takes Eddy's launch kit (titles, description, Shorts, thumbnails) and drafts, schedules, and
tracks the promotional posts/threads around it — always behind an explicit approval gate.

Eddy ships as the **YouTube workflow** in the open-source
[Threadify Workflows](https://github.com/lennoxsaint/Threadify-workflows) library, so an agent can
run "raw footage → finished edit → approved promo schedule" end to end. Eddy stays free and MIT;
Threadify's hosted generation, scheduling, and analytics are the paid layer you opt into.

## Quickstart for creators

Inside Codex, use the plugin install path:

```text
@plugin-creator install [lennoxsaint/eddy](https://github.com/lennoxsaint/eddy)
```

After the plugin finishes installing, attach raw footage and mention:

```text
@Eddy
```

If you attach video footage with no other instructions, Eddy defaults to a YouTube long-form edit
plus Shorts. Single talking-head footage becomes 9:16 Shorts with bottom-third karaoke captions;
separate camera/screen footage uses Eddy's stacked Shorts layout.

Local CLI fallback:

```bash
git clone https://github.com/lennoxsaint/eddy.git
cd eddy
python3 scripts/install_codex.py        # Codex: skill + MCP + local package + Studio Sound
eddy doctor                        # detects hardware, recommends a brain, writes config
eddy studio-sound doctor           # verifies the heavy local voice-enhancement backend
eddy update-check                  # notify-only update check; never pulls or rewrites files
eddy motion update-hyperframes     # pin/index the local HyperFrames registry cache
eddy edit path/to/footage/         # the one-sentence path: proof-gated edit or exact blockers
eddy run path/to/footage/          # lower-level full pipeline control
eddy run talk.mp4 --focus "only keep the part where I explain X"   # topical extract
```

`--install-editable` provisions Eddy's Studio Sound stack by default. The required backend is
DeepFilterNet in Eddy's managed compatible Studio Sound env, followed by candidate-based mouth-click repair, warm
source-first EQ, compression/limiting, and loudness normalization. Eddy renders multiple Studio
Sound profiles (`source_reference`, `warm_room_tame`, `warm_deep_tame`, `warm_click_tame`,
`warm_model_10`, `natural_voice`, and `click_rescue`) and chooses the least harmful candidate.
The source/reference audio is allowed to win. Heavy model output or EQ is not allowed to win just
because one metric improves; it must materially reduce clicks or echo without making the voice feel
worse than the source. If setup fails, Eddy does **not** downgrade silently: full runs fail the audio
quality gate until `eddy studio-sound install` succeeds, or until you explicitly change the audio
policy in config. Resemble Enhance can be installed as an optional experimental backend with
`eddy studio-sound install --include-resemble`. If the agent's Python is too new for Torch/DeepFilterNet,
Eddy uses Python 3.9-3.11 via `EDDY_STUDIO_SOUND_PYTHON` or the first compatible interpreter on PATH.

## Quickstart for Codex or Claude

For Codex, use Plugin Creator:

```text
@plugin-creator install [lennoxsaint/eddy](https://github.com/lennoxsaint/eddy)
```

That installs the repo-shipped plugin from `plugins/eddy/`. The plugin bundles Eddy's skill and MCP
config, then bootstraps the latest stable tagged Eddy engine into `~/.eddy/source` and `~/.eddy/venv`.
Updates are automatic on first use/job start, but only to stable GitHub tags, not `main`.

For older Codex clients or local fallback, run:

```bash
python3 scripts/install_codex.py
```

That installs the root skill plus MCP server from the checkout. For Claude-style skill folders only,
use `scripts/install_agent_skill.py`. Once installed, the agent should call `eddy_edit_options`
before `eddy_edit_start` and fall back to `eddy edit` if tools have not reloaded yet. Eddy either produces local
review outputs or writes an exact blocker, a repair plan, and a redacted support bundle in the run
folder. Full Codex install details:
[docs/CODEX_INSTALL.md](docs/CODEX_INSTALL.md).

Watch progress: `eddy status <run>`. Everything lands in `~/.eddy/runs/<date-slug>/final/launch-kit/`
(configurable via `paths.runs_dir`). Reclaim scratch afterwards with `eddy clean <run>`.
(Pre-0.6 runs lived under `~/Eddy/runs`; move them if you want them under the new default.)

Stage-by-stage instead: `eddy transcribe`, `eddy plan`, `eddy render`, `eddy shorts`, `eddy package`.

Shorts have an editorial gate backed by a baked offline metadata-derived corpus. The repo copy lives
at `docs/references/short-form-hook-playbook.jsonl` and the installable package also ships the same
corpus under `eddy/references/`, so normal edits do not need Supadata or network access. Maintainers
can refresh the corpus with `eddy hooks build-supadata` from supplied public URLs. When only public
YouTube metadata is available, `eddy hooks build-youtube-metadata` builds a weaker title-derived
playbook and labels every record with that provenance instead of pretending it contains
transcript-proven hooks.

Premium motion graphics use `eddy motion init-contract <project-dir>` to write a project-local
`frame.md`, `storyboard.md`, `storyboard.html`, and selected copied HyperFrames references. The
static storyboard must pass before animation/compositing.

Bare `eddy` on a real terminal opens the **full-screen TUI** — Eddy the (chibi) eagle up top, your
runs list, a live run monitor, and a bottom input bar. Type a command (`run <footage>`, `doctor`,
`/help`), or just ask in plain words ("edit my podcast and keep it punchy") and the local brain
interprets it into an action you confirm. **Drag a video onto the input** and add `- only keep the
part about X` to focus the edit — phrasing like "only keep / only focus on" arms an aggressive
topical *extract* (drops the off-topic majority); softer wording is a gentle steer. A focused edit
asks what to produce (just the video / + Shorts / full kit). Launch + watch runs without leaving the app. `eddy tui`
opens it explicitly; `eddy --no-tui` (and any piped / non-TTY / CI / MCP use) prints the branded
banner instead. Preview the mascot with `eddy mascot`; `NO_COLOR=1` / `EDDY_NO_ANIM=1` tone it down.

## Drive Eddy from Claude Code, Codex, or Claude Desktop

Eddy ships an MCP server so an agent can start edits, watch them, and read the launch kit as tools:

```bash
pipx install "eddy[mcp] @ git+https://github.com/lennoxsaint/eddy.git@v1.10.3"
eddy mcp install --client claude-desktop # or claude-code | codex (idempotent, backs up, merges)
```

For Codex users installing from a cloned GitHub repo, prefer `python3 scripts/install_codex.py`
instead. It writes a stable `~/.eddy/bin/eddy-mcp` wrapper and registers Codex without relying on the
desktop app inheriting your shell PATH.

A promise-level edit starts with options: `eddy_edit_options` says whether the host needs to ask,
`eddy_edit_start` returns a `job_id`, `eddy_job_status` polls it, and
`eddy_artifacts` reads the result after completion. Lower-level agents can still use
`eddy_run_start`. There's also a one-shot Claude Code plugin (`/eddy-run`, `/eddy-shorts`,
`/eddy-status` + a skill) at [`integrations/claude-code/`](integrations/claude-code). Full details in
[docs/MCP.md](docs/MCP.md).

## Requirements

- ffmpeg 8+
- Python 3.11+ for Eddy.
- Rust/Cargo for first-time DeepFilterNet builds when a wheel is not available
  (`brew install rust` on macOS, or install from rustup.rs).
- A brain: [Ollama](https://ollama.com) with a ~27B model (best on 32GB+ unified memory),
  or any of: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `codex` CLI, `claude` CLI.
- Optional, thumbnails only: `GEMINI_API_KEY` / `OPENAI_API_KEY` (skipped gracefully if absent).

## Non-Negotiable Output Gates

- No blur/redaction unless you explicitly opt in. If you opt in for privacy redaction, Eddy requires
  a fully opaque solid cover/card; blur and semi-transparent covers are treated as failed redaction.
- No visible PIP/camera blinking around cuts. Shorts camera cuts are covered by the same rule:
  segment renders must use frame-accurate source trim/atrim, and visible talking-head segments must
  be assembled through a re-encoded filtergraph timeline, not concat-copy segment stitching.
- No A/V drift at sampled checkpoints.
- Studio Sound must use a heavy speech-enhancement backend by default; ffmpeg-only EQ/loudness
  polish is a failed quality gate, not a shippable fallback. Heavy cleanup must also pass the
  anti-echo candidate gate; "mouth clicks gone but voice sounds hollow" is not accepted as final.
- No unapproved dead air, retake leftovers, or abrupt audio dropouts.
- Shorts must use separate camera/screen sources when they exist: square camera top, blue karaoke
  captions in the middle, uncropped proof/screen panel bottom.
- Final Shorts require the baked 1,000-hook playbook; missing corpus is a blocker, not a reason to
  output weak clips.
- Premium motion overlays must carry a project-local `frame.md`, copied HyperFrames references,
  lint/inspect/render receipts, collision proof, and visual-taste QA before compositing.

## Status

Open-source under MIT. Eddy never uploads or publishes videos by itself. Product contract:
`docs/PRD.md`. Origin story and decisions: `docs/decision-log.md`.

## For agents

Read `AGENTS.md` first. Hard gates live there.
