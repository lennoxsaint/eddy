---
name: eddy
description: Install and run Eddy, a local-first YouTube editor that turns raw footage into a QA-gated long-form video and only genuinely strong Shorts.
---

# Eddy

Use this skill when the user attaches raw video footage and wants a finished YouTube edit.

Eddy's promise is simple: raw footage in, edited video out. It removes retakes, tightens word gaps, applies local Studio-Sound-style voice cleanup with receipts, renders a long-form YouTube edit, and creates Shorts only when the footage contains standalone Shorts-worthy moments.

Default editorial brain order is Codex/Claude/API first for quality, with local models offered when hardware can support unlimited free editing. Raw media stays local and source files must remain immutable either way.

## First-Time Setup

If this repo is not installed yet and the active agent is Codex, run the one-command Codex bootstrap:

```bash
python3 scripts/install_codex.py
```

This installs Eddy as a **skill plus MCP**: the skill gives Codex the editing rules, and the MCP
server gives Codex tools to start/poll/read edit jobs. It also installs Eddy with the MCP extra and
provisions the local Studio Sound backend unless explicitly skipped.

If this is a Claude-style skill-only install, run:

```bash
python3 scripts/install_agent_skill.py --agent auto --install-editable
```

Then verify:

```bash
eddy doctor
eddy studio-sound doctor
eddy update-check
eddy motion update-hyperframes
```

This installer provisions the heavy local Studio Sound backend unless `--skip-studio-sound` is
explicitly passed. The required default backend is DeepFilterNet in Eddy's managed compatible Studio
Sound env; optional Resemble Enhance support does not replace that gate. If the agent Python is too
new for Torch/DeepFilterNet, Eddy uses Python 3.9-3.11 via `EDDY_STUDIO_SOUND_PYTHON` or the first
compatible interpreter on PATH. If `eddy studio-sound doctor` is not green, do not run a final edit
and call it Studio Sound quality; run `eddy studio-sound install` and fix the exact dependency
blocker first.

## Default Workflow

1. Confirm the user supplied footage and identify camera/screen/audio sources.
2. Run a dry preflight:

```bash
eddy edit /path/to/footage-or-folder --dry-run
```

3. Run the full edit:

```bash
eddy edit /path/to/footage-or-folder
```

Use `eddy run` only when the user explicitly wants lower-level pipeline controls such as topical
extract mode, a named profile, or manual skip flags.

4. Poll/read the run folder under `~/.eddy/runs/<slug>/`.
5. Return exact paths to:
   - `final/long/video.mp4` or the promoted long-form video path Eddy reports
   - `final/transcript.md` when present
   - `final/qa-final.json`
   - `final/shorts/*.mp4` when Eddy found Shorts-worthy moments
   - `final/launch-kit/` when packaging is enabled

For premium motion work, run:

```bash
eddy motion init-contract /path/to/project
```

Then inspect `frame.md`, `storyboard.md`, `storyboard.html`, and the copied HyperFrames manifest
before rendering/compositing motion graphics.

## Hard Rules

- Never mutate source footage.
- Never upload, publish, send, or schedule anything.
- Do not call a run complete unless the QA gates pass.
- If Eddy blocks, report the exact blocker and the smallest next action.
- Do not accept a final unless full watch review is clean or an exact blocker is recorded.
- Studio Sound is a hard audio gate: heavy voice enhancement must be receipt-proven. ffmpeg-only
  loudness/EQ cleanup is a blocker unless the user explicitly lowers the audio policy. Do not
  promote an overprocessed/echoey voice just because clicks are reduced; use the candidate profile
  gate and keep the least processed passing profile. Prefer source-first warm-room profiles when
  heavy enhancement adds room smear; processed audio must not be more echoey than the source. The
  `source_reference` candidate is allowed to win when processing does not produce a material,
  listenable improvement.
- Redaction/blur is opt-in only. Default is fail if blur/redaction appears. When the user explicitly
  asks for privacy redaction, use a fully opaque solid cover/card (`opacity: 1.0` / `alpha: 1.0`).
  Blur or semi-transparent covers are not secure redaction and must fail QA.
- Shorts are optional by quality, not by laziness: output fewer than five if fewer than five clips are genuinely strong.
- Final Shorts require Eddy's baked 1,000-record hook playbook. The repo copy lives at
  `docs/references/short-form-hook-playbook.jsonl`; installed packages also carry it under
  `eddy/references/`. Normal user runs must use it offline. If it is missing or below threshold,
  block Shorts with `short_form_hook_playbook_below_1000_valid_hooks`.
- Long-form and Shorts cuts should be blinkless: tight audio and camera cuts are good, but visual
  flashes around screen or talking-head splices fail QA. For Shorts, do not assemble visible camera
  cuts with concat-copy segment MP4s; use frame-accurate source trim/atrim and a re-encoded
  filtergraph timeline.
- Motion overlays must use a project-local `frame.md` contract plus copied HyperFrames references and collision proof before compositing.

## Editing Standard

- Use the strongest recorded hook.
- Remove alternate hooks, false starts, repeated takes, dead air, and low-value tangents.
- Preserve proof, payoff, context, CTA integrity, and personality moments that help retention.
- Use the approved stacked Shorts layout when separate camera and screen sources exist: square camera top, karaoke captions in the middle, screen/proof panel underneath.
- Apply local Studio-Sound-style cleanup by default: heavy speech enhancement, denoise/dereverb, mouth-click/plosive cleanup, speech EQ, compression/limiting, loudness normalization, A/B samples, and before/after receipts.
