# Research Notes — source truth findings

## Vendored base (yassy-mbp, scp'd 2026-06-11)

- `vendor/yt_tools/` — 16 working scripts from `yassy-mbp:~/YouTube/tools/`. Key constants from
  `render_redesigned_shorts_batch.py` (the approved "Clients Hunt You v3" renderer):
  W,H=1080,1920 · BG=0x07111f · FACE_SIZE=900 @ y=34 · CAPTION_Y=944 H=250 · SCREEN 1000x562 @ y=1254 ·
  RADIUS=34 · GAP_CUT_THRESHOLD=0.68 · START_HANDLE=0.24 · INTERNAL_END_HANDLE=0.32 · FINAL_END_HANDLE=0.52 ·
  GLUED_WORD_GAP=0.08 · shorts markers: "hook for short"/"book for short" variants.
  All 15 files carry hardcoded `/Users/yassybabes/YouTube` ROOTs — parameterization worklist.
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
