# Decision Log

Durable product/architecture decisions. Newest first. Format: date · decision · why.

## 2026-06-11 — Full grilling completed, v1 locked (Claude Code session)

1. **Scope: full launch kit.** Drop footage in → thumbnails + title + edited long + shorts w/ karaoke captions + chapters/description. No publishing.
2. **Loop priority: cut quality first.** Polish only after structure converges.
3. **Approval: after final render.** Fully autonomous run; Lennox reviews the finished kit.
4. **Brain: local-only default (Ollama qwen3.6-27b).** Core promise = free unlimited editing. Five providers ship working: Ollama, Anthropic API, OpenAI API, codex CLI (ChatGPT subscription), claude CLI (Claude subscription).
5. **Architecture: standalone engine** in this repo; Yasmine's proven tooling vendored as the base (`vendor/yt_tools/`, never edited). No Descript, no Chrome MCP, no agent-session coupling.
6. **Transcription: faster-whisper local**, word-level, cached by source hash.
7. **Thumbnails: Gemini + OpenAI images** — the only paid path, cost-logged, skip-with-receipt without keys.
8. **Onboarding: `eddy doctor`** — hardware + credential detection → tier recommendation → config write.
9. **Done gate: deterministic QA + judge ≥8/10, max 5 iterations**, best-attempt shipping with receipts.
10. **Input: camera+screen+mic or single composite** — degraded (no-screen) layout is the primary path.
11. **Two-artifact contract:** model emits Claire-schema remove-list `edit-decisions.json`; deterministic compiler emits video-use-schema `edl.json`. Converter to prior-pipeline benchmark format for objective diffs.
12. **Judge is text-only** — boundary splice cards + stats, defect-list-first, consistency-checked; demotes to advisory if unstable at q4.
13. **Build tracked live on Linear** team EDD, project "Eddy v1", tiny sequenced issues.
14. **Ship-readiness in v1:** pipx-installable, no personal hardcoded paths, stranger-readable quickstart. Public release remains a separate explicit approval.

## 2026-06-10 — First grilling packet (Codex session 019ead42-117d-7aa3-a28c-d8aa5ab1e87b)

- Wedge: **Solo YouTube**. First surface: **Repo Workflow**. Done target: **Publish-Ready Long**.
- Session aborted mid-packet-2; scaffold never created. Recovered and completed 2026-06-11.

## 2026-06-11 — Build-time decisions (autonomous run)

- **Ollama native API over OpenAI-compat shim:** explicit `options.num_ctx=32768` (silent truncation risk on long transcripts) + real JSON-Schema `format` enforcement.
- **Transcription wall-clock:** large-v3 int8 CPU ≈ 2x realtime on M5 Max (~45 min for 23-min video incl. model download). Kept as quality default — runs are autonomous/overnight-capable. Revisit distil-large-v3 if dogfood quality allows.
- **codex_cli adapter verified-blocked locally:** Lennox's `~/.codex/config.toml` has `service_tier = "default"` which the installed codex build rejects. Adapter is correct; environment needs the config fixed. claude_cli adapter verified working end-to-end.
- **Prompts ship inside the wheel** (`src/eddy/prompts/`), `runs_dir` default is `~/Eddy/runs` for strangers; this repo pins `runs_dir=~/eddy/runs` via project `eddy.toml`.

## 2026-06-11 — Dev dogfood results (23-min raw → launch kit, fully autonomous)

- **Outcome:** 23.4-min raw single composite → 13.4-min final long (all deterministic gates pass), 2 karaoke shorts (1080x1920, QA pass), 10 grounded titles, 7 deterministic chapters, description, 2 Gemini thumbnails. Source hash verified untouched.
- **Loop behavior:** 5 iterations, best attempt = iter 4 (gates ✓, judge 5.1). Judge at q4 plateaus ~4.5–5.5 and inflates defect counts — absolute calibration unreliable, defect lists still useful for directives. Runs ship via best-attempt path as designed.
- **Policy fixes shipped during the run:** protected-moments win deterministically (clip cuts, never bounce contradictions to the model); dead air inside protected demo moments is a visual beat, not a defect; handles hard-fail only below the 30ms fade floor; freezedetect at 60s for static screen content; target clamps to feasible speech duration.
- **Wall-clock:** ~70 min total post-transcript (5 iterations × ~6–8 min incl. qwen calls + proxy renders, final render ~7 min, shorts ~4 min, packaging ~5 min).
