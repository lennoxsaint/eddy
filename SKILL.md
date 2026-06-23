---
name: eddy
description: Install and run Eddy, a local-first YouTube editor that turns raw footage into a QA-gated long-form video and only genuinely strong Shorts.
---

# Eddy

Use this skill when the user attaches raw video footage and wants a finished YouTube edit.

Eddy's promise is simple: raw footage in, edited video out. It removes retakes, tightens word gaps, applies local Studio-Sound-style voice cleanup with receipts, renders a long-form YouTube edit, and creates Shorts only when the footage contains standalone Shorts-worthy moments.

Default editorial brain order is Codex/Claude/API first for quality, with local models offered when hardware can support unlimited free editing. Raw media stays local and source files must remain immutable either way.

## First-Time Setup

If this repo is not installed yet, run:

```bash
python3 scripts/install_agent_skill.py --agent auto
python3 -m pip install -e .
eddy doctor
eddy studio-sound doctor
eddy update-check
```

For a one-command agent setup from the repo root:

```bash
python3 scripts/install_agent_skill.py --agent auto --install-editable
```

This installer provisions the heavy local Studio Sound backend unless `--skip-studio-sound` is
explicitly passed. The required default backend is DeepFilterNet; optional Resemble Enhance support
does not replace that gate. If `eddy studio-sound doctor` is not green, do not run a final edit and
call it Studio Sound quality; run `eddy studio-sound install` and fix the exact dependency blocker
first.

## Default Workflow

1. Confirm the user supplied footage and identify camera/screen/audio sources.
2. Run a dry preflight:

```bash
eddy run /path/to/footage-or-folder --dry-run
```

3. Run the full edit:

```bash
eddy run /path/to/footage-or-folder
```

4. Poll/read the run folder under `~/.eddy/runs/<slug>/`.
5. Return exact paths to:
   - `final/video.mp4`
   - `final/transcript.md` when present
   - `final/qa-final.json`
   - `final/shorts/*.mp4` when Eddy found Shorts-worthy moments
   - `final/launch-kit/` when packaging is enabled

## Hard Rules

- Never mutate source footage.
- Never upload, publish, send, or schedule anything.
- Do not call a run complete unless the QA gates pass.
- If Eddy blocks, report the exact blocker and the smallest next action.
- Do not accept a final unless full watch review is clean or an exact blocker is recorded.
- Studio Sound is a hard audio gate: heavy voice enhancement must be receipt-proven. ffmpeg-only
  loudness/EQ cleanup is a blocker unless the user explicitly lowers the audio policy.
- Redaction/blur is opt-in only. Default is fail if blur/redaction appears.
- Shorts are optional by quality, not by laziness: output fewer than five if fewer than five clips are genuinely strong.
- Long-form screen cuts should be blinkless: tight audio and camera cuts are good, but visual flashes around screen splices fail QA.
- Motion overlays must use a project-local `frame.md` contract plus copied HyperFrames references and collision proof before compositing.

## Editing Standard

- Use the strongest recorded hook.
- Remove alternate hooks, false starts, repeated takes, dead air, and low-value tangents.
- Preserve proof, payoff, context, CTA integrity, and personality moments that help retention.
- Use the approved stacked Shorts layout when separate camera and screen sources exist: square camera top, karaoke captions in the middle, screen/proof panel underneath.
- Apply local Studio-Sound-style cleanup by default: heavy speech enhancement, denoise/dereverb, mouth-click/plosive cleanup, speech EQ, compression/limiting, loudness normalization, A/B samples, and before/after receipts.
