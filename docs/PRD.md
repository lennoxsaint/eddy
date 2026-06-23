# PRD: Eddy — Local-First Agentic Video Editor

Status: ready-for-agent · Owner: Lennox Saint · Tracker: Linear team EDD · Version: 1.0 (2026-06-11)

## Problem Statement

As a solo YouTube creator, every raw recording I make is full of retakes, false starts, long word gaps, and messy creator-recording texture. Turning one raw recording into a publishable launch package today requires hours across Descript, manual cut review, shorts composition, caption styling, thumbnail tooling, and packaging copy — or a brittle chain of agent skills coupled to a browser session. The editing cost, not the recording cost, is the bottleneck on output. Cloud editing tools also charge per use, so volume is punished.

## Solution

Eddy is a local-first CLI app: drop raw footage in (`camera.mp4` + `screen.mp4` + optional `mic.wav`, or a single composite recording), and a local model loops — transcript → cut plan → simulation → proxy render → QA → judge — until the edit is actually done, then produces the complete launch kit with zero human input until final review:

- edited long video (publish-ready)
- shorts with blue karaoke captions in the approved stacked layout
- thumbnail candidates (the only paid-API step)
- 10 grounded title candidates
- chapters + YouTube description

The editorial brain is a local Ollama model by default (free unlimited editing — the core promise). Hardware-aware onboarding (`eddy doctor`) detects the machine and recommends one of five working provider tiers: Ollama local, Anthropic API, OpenAI API, codex CLI (ChatGPT subscription), claude CLI (Claude subscription). Every decision, model call, render command, and QA verdict is written to receipts. Sources are never mutated. Nothing is ever published automatically.

## User Stories

1. As a solo YouTube creator, I want to drop a raw recording into one command, so that I get a complete launch kit without touching an editor.
2. As a creator, I want retakes and false starts removed automatically with last-take bias, so that the final cut keeps my best delivery without me scrubbing the timeline.
3. As a creator, I want long word gaps and dead air tightened while natural micro-pauses survive, so that the video is paced well but still feels human.
4. As a creator, I want the edit loop to iterate autonomously and only show me the finished result, so that my time is spent reviewing, not supervising.
5. As a creator, I want a deterministic QA gate (no clipped words, no dead air, duration in band, clean streams), so that mechanical defects can never ship regardless of model quality.
6. As a creator, I want an AI judge to score editorial quality against a rubric before the final render, so that pacing and narrative continuity problems get fixed in the loop, not in my review.
7. As a creator, I want the loop to keep repairing and rerendering until gates pass, stopping only for an impossible blocker with exact evidence, so that I wake up to a real finished edit instead of a sample.
8. As a creator, I want shorts auto-extracted from marked hook moments and edit decisions, so that vertical content ships alongside every long video.
9. As a creator, I want shorts rendered in my approved layout (face panel, blue karaoke captions, screen panel, navy background), so that my brand style is preserved without per-video styling work.
10. As a creator, I want karaoke captions driven by word-level timestamps, so that the current word highlights exactly in sync with speech.
11. As a creator, I want each short to end on a complete sentence and complete thought, so that no short ships with a dangling setup.
12. As a creator, I want thumbnail candidates generated from sharp face frames of the actual video, so that thumbnails look like the video they sell.
13. As a creator, I want 10 title candidates grounded in transcript quotes, so that titles are claims the video actually supports.
14. As a creator, I want chapters derived deterministically from the beat map with model-written labels only, so that chapter timestamps are never hallucinated.
15. As a creator, I want a YouTube description drafted with chapters embedded, so that the upload form is a paste job.
16. As a privacy-conscious user, I want transcription and editorial reasoning to run fully locally by default, so that my raw footage never leaves my machine.
17. As a cost-conscious user, I want unlimited editing at zero marginal cost on my own hardware, so that volume is rewarded, not billed.
18. As a new user on a weak machine, I want `eddy doctor` to detect my hardware and recommend the best brain tier, so that onboarding gives me a working setup instead of a failed local model.
19. As a ChatGPT subscriber, I want Eddy to use my existing subscription via the codex CLI, so that cloud-quality editing costs me nothing extra.
20. As a Claude subscriber, I want the same via the claude CLI, so that my plan powers my editing.
21. As an API user, I want Anthropic and OpenAI API adapters with a cheapest-capable default model, so that I can choose cost/quality explicitly.
22. As a user, I want every provider behind one interface with per-run override, so that switching brains is a config change, not a migration.
23. As a returning user, I want runs to be resumable after a crash, so that a 54-minute video doesn't restart from zero.
24. As a user, I want a receipts log of every model call, ffmpeg command, gate result, and cost, so that I can audit what the agent did and why.
25. As a user, I want my source files guaranteed untouched (hash-verified before and after), so that a bad run can never destroy footage.
26. As a user, I want thumbnails to skip gracefully with a logged receipt when API keys are absent, so that the kit still ships.
27. As a user, I want `eddy run` to work on a single composite recording (no separate screen track), so that any recording setup is supported with a gracefully degraded layout.
28. As a power user, I want stage-level commands (`eddy transcribe`, `eddy plan`, `eddy render`, `eddy shorts`, `eddy package`), so that I can re-run one stage without repeating the pipeline.
29. As a new external user, I want to install Eddy from the public GitHub repo and be editing within minutes via a stranger-readable quickstart, so that the app is shippable to a thousand users, not just its author.
30. As the product owner, I want Eddy's cut decisions benchmarked against my prior human-in-the-loop pipeline on the same video, so that quality claims are receipts, not vibes.
31. As the product owner, I want public-safe docs, a root skill, and install checks, so that Codex or Claude can install the repo from a link and edit attached footage unattended.

## Implementation Decisions

- **Two-artifact editorial contract.** The model emits a remove-list `edit-decisions.json` (Claire schema v1.0: text-anchored cuts in MANDATORY/RECOMMENDED/OPTIONAL tiers, retake adjudications with last-take bias, protected moments, shorts candidates). A deterministic compiler emits the keep-list `edl.json` (video-use schema v1: source ranges with beats/quotes/reasons). Models reason about quoted text; renderers consume only compiled ranges.
- **Compiler owns all mechanical invariants:** word-boundary snapping with 50/80ms pads, no range under 1.2s, ranges sorted/merged, 30ms audio fades at every boundary, per-segment extract then lossless `-c copy` concat. Model output that violates invariants is returned as a structured error for delta repair (max 2 attempts).
- **The agentic loop separates judgment from mechanics.** Model-driven: beat map (once), cut decisions, delta revisions responding to typed defect directives (`restore | extend_pad | tighten_gap | drop_beat | swap_take | trim_tail`). Deterministic: everything else. Revisions are always deltas against the previous decisions — never from-scratch replans — to prevent oscillation.
- **Tiered QA pyramid, cheap to expensive:** tier 0 transcript simulation (duration band, mid-word cuts, protected moments, dead air); tier 1 boundary audio probes (clipped-word and pop detection); tier 2 480p proxy + contact sheet (stream-clean, A/V drift, black/freeze detection); tier 3 one full-res final render on the best attempt only.
- **Text-only judge, honestly designed.** The judge never claims to watch video. Evidence packet: cut transcript with beats, per-boundary splice cards (last words kept → cut summary → next words kept), stats block, "what was lost" summaries. Rubric: hook integrity ×2, boundary continuity ×3, pacing ×2, completeness/no-orphans ×2, ending+CTA ×1. Defect-list-first output via JSON schema, temperature 0.2, code-side consistency checks (score/defect mismatch → resample once → take min and flag `judge_unstable`). If unstable at q4 quant, judge demotes to advisory; deterministic gates always required independently.
- **Done gate:** all deterministic gates pass AND judge >= 8/10. The loop keeps revising until the gate passes or records an impossible blocker (`missing_source`, `corrupt_source`, `missing_dependency`, or repeated identical failure after changing strategy). Best-attempt shipping is not allowed when `require_gate_pass` is true.
- **Five working providers behind one protocol** (`complete(messages, schema?) → text|dict`): Ollama via OpenAI-compatible endpoint (default, qwen3.6-27b), Anthropic API (Haiku-class default), OpenAI API, codex CLI subprocess (ChatGPT subscription), claude CLI subprocess (Claude subscription). `eddy doctor` detects chip/RAM, Ollama models, credentials and CLIs, then recommends and writes the tier.
- **Shorts render ports the proven standard** (`vendor/yt_tools/` read-only references): 1080×1920 stacked layout, square face panel in the top half, karaoke caption zone in the gap, screen panel in the bottom half, navy background, blue current-word highlight, spoken/future word dimming; audio-safe handles 0.24s start / 0.32s internal / 0.52s final; sentence-final QA ledger per short. Degraded single-composite layout is allowed only when no separate screen track exists.
- **Chapters are deterministic** (beat map mapped to output timeline); the model writes only the 2–5 word labels. Title candidates must carry the transcript quote that grounds them.
- **Thumbnails are the only paid path:** sharpest face frames (Laplacian ranking) at high-energy moments → Gemini image API + OpenAI image API, N candidates each, cost logged per call, skip-with-receipt when keys are absent.
- **Run state is files:** per-run directory with manifest (source sha256 + config snapshot), transcript artifacts, per-iteration artifacts (decisions, EDL, sim report, proxy, QA, judge, directive), `state.json` for resume, append-only `receipts.jsonl`, and a `final/launch-kit/` output.
- **Hard gates enforced in code:** sources opened read-only and hash-verified before/after every run; every ffmpeg output path asserted inside the run directory; no publish/upload integration exists in v1; public distribution requires scrub checks and MIT docs to pass first.
- **Config:** `eddy.toml` (tomlkit round-trip; doctor updates only hardware-derived sections), provider/loop/render/shorts/thumbnails/gates sections; ship-ready defaults resolve to `~/.config/eddy/` with project-local override.

## Testing Decisions

- Tests assert external behavior only: artifact contents, schema round-trips, gate verdicts — never internal call order.
- **Compiler invariants** get the densest tests (synthetic transcripts → decisions → EDL): word-boundary snapping, pad math, merge/sort, minimum-range rejection, text-anchor misses produce structured errors.
- **Schemas:** decisions and EDL round-trip through pydantic; benchmark-format converter is property-checked (ranges preserved, times monotonic).
- **Gate logic:** deterministic QA verdicts on crafted sim reports/probe stats; judge consistency checks (inflated score + major defects → resample path) with a stubbed provider.
- **Loop controller:** termination (≤5 iterations), best-attempt ranking, resume from `state.json` — all with stubbed provider and stubbed renderer.
- Render/transcribe stages are verified by the per-phase dogfood gates (real ffprobe/playback checks), not unit tests.
- Prior art: contract-style artifact validation as in the content-pipeline QA skills (edit-qa.json gates); no existing pytest suite to mirror — this repo sets the pattern.

## Out of Scope

- Publishing or uploading anywhere (YouTube, podcast, anything) — manual-review doctrine; no publish code in v1.
- Codex plugin surface, watch-folder daemon, drag-drop GUI — phase 2.
- Public release to GitHub/PyPI — packaged and ready in v1, but the release itself is a separate explicit approval.
- HyperFrames-style branded motion overlays, color grading, music — polish layers, phase 2.
- Multi-speaker / interview formats — v1 is solo creator footage.
- Vision-model judging of rendered frames — judge is text-only by design until a vision path is proven.

## Further Notes

- Dogfood targets: dev loop on the 23-min 61MB `2026-06-04-daily-greatest-hits` raw video; full dogfood on the 54-min 1.3GB `2026-06-10-fable-mythos-permissions` raw video, which has a prior-pipeline `edit-decisions.json` to diff against (kept-range overlap %, beat coverage, duration delta).
- Top risks, ranked: (1) shorts renderer port with single-composite degraded layout as primary path, (2) judge reliability at q4 quant, (3) 27b editorial quality over a 54-min transcript, (4) wall-clock on full dogfood, (5) vendored-code dependency (already mitigated — vendored and committed).
- The vendored `vendor/yt_tools/` originals are never edited; they are the diff anchor for every port.
- Origin: Codex session `019ead42-117d-7aa3-a28c-d8aa5ab1e87b` (Jun 10, 2026), grilling completed in Claude Code session of Jun 11, 2026. Full decision table in `docs/decision-log.md`.
