# Eddy V3 — one lightweight editing skill

Drop in raw footage, say **"edit this"**, get a finished YouTube long (16:9 1080p) + 3–5 Shorts +
1–2 alternate hook cold-opens — good enough to ship without review.

V3 is a distillation of what V1 and V2 got right, with none of their bloat:
- **V1's look** — rounded-corner webcam PiP over screen recording, clean cyan/white karaoke,
  Shorts stack. Done in ffmpeg (`scripts/composite_render.py`).
- **V2's audio** — real Descript Studio Sound via API, audio-only (`scripts/descript_studio_sound.py`).
- **The model's taste** — every editorial choice (hook, cut list, retakes, clarity, layout) is made
  by whatever agent invokes the skill (Opus / GPT-5.x). The instruction set is deliberately minimal.

## How it runs

The `SKILL.md` is the whole brain (a "mega prompt"); `references/` holds the doctrine loaded on
demand; `scripts/` holds the frozen mechanics. Flow: transcribe → beat map → **hook hunt (90% of the
effort)** → body edit → Descript Studio Sound → scoped HTML motion layer → composite → Shorts →
proxy render → verify + self-heal (≤3) → ship. See `SKILL.md`.

## Frozen helpers (mechanics only)

| Script | Does | Distilled from |
|---|---|---|
| `scripts/transcribe.py` | word-level transcript | WhisperX (caption-gen venv) |
| `scripts/splice.py` | execute the cut list + tighten gaps >0.2s→0.1s | V1 cut-handle math |
| `scripts/descript_studio_sound.py` | Studio Sound (audio only) + parity | eddy-v2 `audio.py` |
| `scripts/composite_render.py` | rounded-corner PiP layout + Shorts stack + proxy/full | eddy-v1 `render/` |
| `scripts/verify.py` | deterministic gates | eddy-v1 QA |

Motion + captions reuse the existing **HyperFrames** and **embedded-captions** (`anchor`) skills.

## Requirements

- `ffmpeg` / `ffprobe`, Python 3.12 with `Pillow`.
- `DESCRIPT_API_KEY` exported (Studio Sound is non-negotiable). Dev-only offline approximation:
  `EDDY_FAKE_DESCRIPT=1` (never ship that output).
- WhisperX venv at `~/content-tools/caption-gen/.venv`.
- `npx hyperframes` available for the motion layer.

## Status

Prompt layer (SKILL.md + references) is complete and is the source of truth. Frozen helper scripts
are first-draft, faithful to the V1/V2 source; the exact rounded-corner inset/radius and the splice
crossfade are the tuning points to validate on a real recording (see the plan's verification step).

Maintained as a standalone skill and a git repo. Never publishes; never overdubs; never guts a video.
