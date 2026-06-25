# Research Notes — source truth findings

## Vendored base (local reference import, 2026-06-11)

- `vendor/yt_tools/` — 16 working scripts copied from a prior local YouTube editing workflow. Key constants from
  `render_redesigned_shorts_batch.py` (the approved "Clients Hunt You v3" renderer):
  W,H=1080,1920 · BG=0x07111f · FACE_SIZE=900 @ y=34 · CAPTION_Y=944 H=250 · SCREEN 1000x562 @ y=1254 ·
  RADIUS=34 · GAP_CUT_THRESHOLD=0.68 · START_HANDLE=0.24 · INTERNAL_END_HANDLE=0.32 · FINAL_END_HANDLE=0.52 ·
  GLUED_WORD_GAP=0.08 · shorts markers: "hook for short"/"book for short" variants.
  Public-readiness hardening later sanitized those reference constants too: `EDDY_YT_TOOLS_ROOT`,
  `EDDY_YT_TOOLS_PY_ROOT`, `FFMPEG`, and `FFPROBE` now stand in for the original local paths. Runtime
  Eddy code must stay parameterized and must not import those scripts as live entrypoints.
- `docs/references/shorts-rendering-standard.md` — the approved spec (layout, karaoke caption behavior,
  edit standard incl. 0.10s hard-fail boundary handles, QA gate incl. sentence-final ledger).

## Local contracts reused

- video-use EDL v1 (`~/.agents/skills/video-use/SKILL.md`): `{version, sources, ranges:[{source,start,end,beat,quote,reason}], subtitles, total_duration_s}`; hard rules: word-boundary cuts, 30–200ms pads, 30ms afades, per-segment extract → `-c copy` concat, subtitles last.
- Claire edit-decisions v1.0 (`~/.claude/skills/claire/SKILL.md`): remove-list, transcript-text-anchored, tiers MANDATORY/RECOMMENDED/OPTIONAL, last-take bias, protected_moments, shorts_candidates.
- Prior-pipeline benchmark (`~/content-pipeline/2026-06-10-fable-mythos-permissions/source/edit-decisions.json`): keep-list `{slug,title,source_video,ranges:[{start,end,duration,beat,reason}]}` — flattened-EDL shape, used for the P9 diff.

## Environment (verified)

- M5 Max, 18-core, 128GB unified. ffmpeg 8.0 + ffprobe (brew). Python 3.12.11.
- Ollama live at :11434 with `qwen36-27b-codex:q4` (51GB), gemma4-31b, qwopus35-27b, gpt-oss:120b, all-minilm.
- Dev video: `~/content-pipeline/2026-06-04-daily-greatest-hits-system-on-threads/source/raw/raw-video.mp4` — 61MB, ~23min, 1114x720@30, single composite (no separate screen track).
- Full dogfood: `~/content-pipeline/2026-06-10-fable-mythos-permissions/source/raw/raw-video.mp4` — 1.3GB, ~54min, single composite, has prior-pipeline benchmark artifacts.
- Linear: workspace w/ team EDD via `LINEAR_API_KEY`; project "Eddy v1" `c3bf1890-355c-467e-a930-97a89aeaa5bf`; issues EDD-5..EDD-49.

## Open questions / watchlist

- qwen3.6-27b structured-output reliability at q4 — validated by `eddy doctor --ping`; judge demotes to advisory if unstable.
- faster-whisper large-v3 wall-clock on 54-min audio — consider distil-large-v3 if >45min.
- "Codex app server" proper integration (vs `codex exec` subprocess) — revisit when plugin surface lands (phase 2).

## One-sentence install surface (2026-06-25)

- `eddy edit` is the public promise command: prepare sources, select a template, route the brain,
  verify hook/motion/audio prerequisites, and either render through the existing autonomous pipeline
  or emit exact blockers with `one-sentence-state.json` and a redacted `support-bundle.zip`.
- `eddy_edit_start` is the MCP equivalent for Codex/Claude. `eddy_run_start` stays available for
  lower-level/manual control.
- The baked hook playbook is duplicated into `src/eddy/references/` and included as package data so
  GitHub-source installs can run Shorts selection offline even when the installed wheel no longer has
  the repo `docs/` tree beside it.

## Codex install surface (2026-06-25)

- OpenAI release notes describe Codex plugins as bundles that can package skills, app integrations,
  and MCP server configuration. Eddy now ships that bundle under `plugins/eddy/`.
- Current public Eddy share path: `@plugin-creator install
  [lennoxsaint/eddy](https://github.com/lennoxsaint/eddy)`. The plugin entry uses a Git-backed
  subdirectory source and pins stable tags rather than `main`.
- `scripts/install_codex_plugin.py` writes or previews a personal marketplace entry pointing at
  `plugins/eddy/`. `scripts/install_codex.py` remains the skill+MCP fallback for older Codex clients
  and local development.
- The plugin wrapper auto-updates `~/.eddy/source` and `~/.eddy/venv` from stable `vX.Y.Z` tags only,
  smoke-checks before swapping, and records blockers in `~/.eddy/plugin-state.json`.
- Single-source Shorts now default to `talking_head_916`: 1080x1920 crop/fill, face-centered source,
  blinkless re-encoded segment assembly, and karaoke captions in the bottom third.
