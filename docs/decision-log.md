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

## 2026-06-11 — Full dogfood results (54-min raw → launch kit) + v0.1

- **Outcome:** 54.3-min dense-talk raw → 28.8-min final long (all deterministic gates pass, judge 6.2 best-attempt), 3 karaoke shorts (QA pass), 10 titles, 7 chapters, description, 2 Gemini thumbnails. Sources hash-verified untouched.
- **Benchmark vs prior human-loop pipeline (same video):** Eddy 28.8 min / 31 ranges vs prior 24.8 min / 16 ranges; overlap 15.6 min = 62.9% of the prior edit's selections. Directionally aligned, real divergence on ~40% of selections — `final/benchmark-diff.json` has the regions.
- **Critical fix discovered here:** the model protects whole beats wall-to-wall; protection semantics changed to "the majority of a protected span must survive" — otherwise broad protections void every cut and the edit silently keeps ~everything.
- **Judge calibration (q4 27b) across both dogfoods:** plateaus 5–7, never reaches the 8.0 gate; runs ship via best-attempt as designed. Deterministic suite is the effective gate; judge defect lists still drive useful revisions (duration convergence 53.7 → 29.3 min came from directive-driven structural cuts).

## 2026-06-16 — v1.0 GA hardening (autonomous run) + EDD-84 disposition

- **Ledger reality:** this autonomous build tracked progress in `BUILD-STATE.md` (compaction-proof, in-tree) rather than live Linear issues — the Linear path (`scripts/linear.py`) requires a remote + key that is a human-gate item. So Linear issue IDs referenced in the plan (incl. **EDD-84**) were NOT mutated by this run.
- **EDD-84 — documented, not silently closed:** EDD-84 is an external Linear (team EDD) tracking item from the production-readiness audit. Its exact body was not reconcilable inside this offline build (no verified Linear access this session), so it is explicitly **carried into the human-gate batch** for reconciliation: when the private remote + Linear key exist, reconcile EDD-84 (and the rest of team EDD) against the actually-shipped v0.4→v1.0 work recorded in `BUILD-STATE.md` and the git tags. It is referenced as an open item in `docs/KNOWN-LIMITS.md`. No claim is made here that EDD-84's specific defect was fixed — only that it is tracked and routed to reconciliation.
- **GA docs added:** `docs/RELEASE.md` (required-green gate + signing/notarize human-gate + update/rollback), `docs/SUPPORT.md` (triage runbook: doctor → dry-run → bundle), `docs/KNOWN-LIMITS.md` (honest scope boundaries), `docs/REPRODUCIBILITY.md` (two-tier model + exact-mode seed), `docs/AIRGAP.md` (offline wheelhouse + model staging).

## 2026-06-16 — v1.1 "Eddy's Face": mascot + MCP server + Claude Code plugin

- **Eddy is a bald eagle, rendered as real pixel art.** Box-drawing glyphs read as an owl/blob, so the sprite is a palette-indexed **bitmap** drawn with the half-block trick (`▀`, fg=top px / bg=bottom px) — true 8-bit image fidelity in the terminal. The eagle design was iterated against rendered PNGs and **visually confirmed** (white head, yellow eye + brow, hooked gold beak with a dark gape line, brown folded-wing body, gold talons) — cute, not fierce. Hero + compact sizes, 5 states. Plain-ASCII fallback when colour is off (`NO_COLOR`/non-TTY/pipe), since half-blocks need colour. `src/eddy/ui/{pixels,sprite,wordmark,console,animate}.py`.
- **Wake screen.** Bare `eddy` now wakes the mascot (branded splash + recent runs + next steps) instead of dumping help; `eddy --help`/`--version` unchanged. `eddy mascot` previews states/animation. Animation is strictly gated (real TTY + not `EDDY_NO_ANIM`), so pipes/CI/the MCP subprocess get clean lines.
- **MCP server (`eddy-mcp`), hybrid by design.** Long mutating ops (run/shorts/transcribe/render/batch) run as **subprocess jobs** (`python -m eddy …`, `EDDY_NO_ANIM=1`) — fire-and-poll (`eddy_run_start`→`eddy_job_status`→`eddy_artifacts`) so a 5–15 min edit never blocks a tool call, each run's egress/offline state is isolated, and the hardened CLI path is reused. job_id = run slug ⇒ deterministic run dir. Cheap reads run in-process under a `redirect_stdout(→stderr)` guard so a stray print can't corrupt the stdio JSON-RPC stream (reviewer verified 0 bytes on stdout empirically). Destructive tools (`clean`/`purge`) refuse without `confirm=true`. 17 tools. `src/eddy/mcp_server/`.
- **Distribution decision:** `mcp` is an **optional extra** (`eddy[mcp]`) so the base install stays slim/offline-friendly; `eddy-mcp` is a new console script. `eddy mcp install --client claude-desktop|claude-code|codex` writes config idempotently (backs up, merges only the `eddy` key — JSON or comment-preserving TOML). A one-shot Claude Code **plugin** ships at `integrations/claude-code/` (commands + `eddy` skill + `.mcp.json`). No marketplace/PyPI publish — owner-gated.
- **Adversarial review (superpowers:code-reviewer) verdict: MERGE.** Fixed before tag: **M1** job-id collision (two live same-source runs could share a run dir and race `state.json`) → `_launch` refuses a live duplicate + `start_*` auto-uniquify the slug; **M3** `eddy_artifacts` tolerates corrupt JSON; corrected a false "no pings" docstring. **M2** (cancel only works within the originating server session) documented as session-scoped; disk-backed pid registry deferred to v1.1.x.
- **Tags/version:** branch `v1.1-eddy-face` ff-merged to `master` locally (no push, per AGENTS.md), tagged `v1.1.0`, `pyproject` 1.0.0→1.1.0. Suite 464→532 green; coverage 70.5% (floor 67); ruff + mypy clean. `vendor/yt_tools/` untouched.

## 2026-06-16 — v1.2 "Eddy Lands": full-screen TUI + chibi eaglet + upright wordmark

- **Bare `eddy` opens a full-screen Textual TUI** (Lennox: "like Claude Code, not just a box at the
  top"). Hybrid layout: animated chibi-eaglet header, a live runs list, a run monitor, and a bottom
  input bar. Reverses v1.1's "banner only, no Textual" — Textual is now a **core dependency** and the
  TUI is the default interactive experience. Piped / non-TTY / `--no-tui` / CI / the MCP subprocess
  still get the v1.1 banner (`_wake()` gates on `stdout.isatty()`), so automation is untouched. `eddy
  tui` launches it explicitly.
- **Input bar is hybrid**: a deterministic command/`/slash` parse first (instant, no model call);
  unrecognised text falls back to **local-brain NL interpretation** (`interpret_nl`, JSON schema, run
  in a Textual worker thread) into a structured action. Every NL action — and every long/destructive
  action — goes through a **confirm modal** before executing, so Eddy never acts on a guess or deletes
  anything without a yes.
- **Mascot is now a cute chibi/kawaii baby bald eaglet** (big round white head, huge sparkly eyes,
  blush, small hooked gold beak) — the v1.1 realistic bust read as stern. Iterated against rendered
  PNGs and confirmed visually; states (idle/thinking/working/success/error) are eye-row overrides on
  the base bitmap. The **EDDY wordmark is upright** now (dropped the shear), not italic.
- **Refactor**: `Job`/`JobManager` moved from `eddy.mcp_server.jobs` to core **`eddy.jobs`** (no
  MCP-SDK deps) so the TUI launches/monitors runs via the same subprocess job model without the
  optional `mcp` extra; `eddy.mcp_server.jobs` re-exports for back-compat.
- **Testing**: the TUI is covered by Textual's `run_test` pilot harness (mount, run→confirm→job,
  cancel, doctor modal, quit, eagle state) plus pure-logic tests for intents/runner/eagle.
  `asyncio_mode=auto`; `tui/*.tcss` added to package-data. Note: the `EagleWidget` and `DoctorScreen`
  must override `render()` only (not Textual's internal `_render`) — a `_render(self, …)` override
  silently breaks Textual rendering (caught in review/tests).
- **Ship**: branch `v1.2-eddy-tui` ff-merged to `master` locally (no push), tagged **v1.2.0**,
  `pyproject` 1.1.0→1.2.0, `requirements.lock` += textual deps. Suite 532→562 green; coverage 71.0%
  (floor 67); ruff + mypy clean. `vendor/yt_tools/` untouched.

## 2026-06-17 — Eddy on GitHub + trunk-based workflow

- **Private GitHub remote, trunk-based on `main`.** Repo pushed to a **private** `origin`
  (`lennoxsaint/eddy`) at Lennox's explicit request; default branch renamed `master`→`main`; full
  history + all tags (`v0.1`→`v1.2.0`) pushed. Workflow is now **commit straight to `main`, no PRs**
  (Lennox: "work on main to save time"). `AGENTS.md`'s old "no pushing code" gate is replaced with this
  rule; the protective intent stays (no PUBLIC repo, no package publish, no external messages, no new
  paid jobs without approval).
- **CI earned its keep immediately.** The first push surfaced a real GA-portability bug:
  `resolve_video_encoder()` trusted `ffmpeg -encoders`, but `h264_nvenc` compiles into most Linux/CI
  ffmpeg builds yet can't run without a CUDA GPU — every render on a GPU-less host died with "Cannot
  load libcuda.so.1". Fixed: `_available_encoders` now **runtime-probes** each HW encoder (1-frame null
  encode) and drops dead ones, so GPU-less hosts fall back to `libx264`; macOS still picks videotoolbox.
- **CI ffmpeg version.** Eddy requires ffmpeg **8+** (documented; the av-drift overrun on 7.x proves
  render timing differs). ubuntu-latest apt ships 6.x and `setup-ffmpeg`'s Linux build lags, so the
  Linux CI legs now pull **BtbN's current static build**; macOS/Windows keep `setup-ffmpeg`. CI green.

## 2026-06-17 — v1.3 "Eddy, simpler": TUI minimalism + honest feedback + reach

- **Why:** a 6-agent review (+ screenshot) found the v1.2 TUI over-explained itself (command/key hints
  printed 3×) while under-serving a non-technical creator (raw `run/phase` columns + phantom empty row,
  engine internals like `gates ✗`, and — worst — the eaglet showed the *happy* bird even when a run
  failed). Lennox approved implementing **all** review items autonomously.
- **Visual minimalism** (`home.py`, `app.tcss`): one warm `_WELCOME` (full reference moved to `/help`),
  the in-body key line deleted (Footer owns keys), a plain one-line placeholder, a teaching empty state
  (`#runsempty`), a labelled (`border_title`) runs box with a **slate** border (gold moved to the input
  bar — the call to action), a compact 2-line header (the chibi eaglet's ~8-row sprite floors header
  height, so the win is the title collapse, not clipping the locked mascot), de-jargoned copy.
- **Honest feedback** (`phases.py`, `runner.py`, `home.py`): the eaglet now shows the **sad bird** on a
  failed run (reads `JobManager.status` → `failed`) + a one-time notify with the log tail; the monitor
  leads with a **human verdict** ("Kept the best of N passes") and demotes raw judge/gates numbers;
  engine phase slugs render as **plain labels** with "(step k of N)".
- **Functional reach**: `open` **reveals** results in the OS file manager (`open`/`xdg-open`/`startfile`
  — a local folder, not a URL); a **live log tail** streams into the monitor during runs; **ctrl+x**
  cancels a run (confirm-gated); interrupted runs show a **resume** hint; inline **autocomplete** for
  verbs, run slugs, and filesystem paths; mascot **ASCII fallback** below 256 colours; Refresh/Doctor
  moved off terminal-reserved `ctrl+r`/`ctrl+d` to **F5**/**F2**; confirm + doctor modals show their
  keys; the redundant **command palette is disabled** (the input bar already does everything).
- **Ship**: committed straight to `main` (trunk-based, no PR), tagged **v1.3.0**, `pyproject`
  1.2.0→1.3.0. Suite 562→581 green; coverage 71.4% (floor 67); ruff + mypy clean; **CI green** on the
  hosted runner. `vendor/yt_tools/` + the locked eaglet/brand untouched.

## 2026-06-17 — v1.4 "No Sharp Edges": verified crash/leak fixes + in-app UX + test debt

- **Why:** with the v0.4→v1.0 GA march done and v1.3 shipped, a 7-subsystem assessment (Workflow
  fan-out, each finding re-verified against source) found Eddy GA-solid but with five real,
  source-confirmed crash/leak paths and a thin in-app failure/preview UX. Lennox approved shipping the
  whole batch autonomously, trunk-based on `main`.
- **Verified crash/leak fixes (batch 1):** UTF-8-hardened stdout/stderr (`ui/console.harden_stdout`,
  wired into CLI/TUI entry) so a legacy Windows cp1252 console never dies on Eddy's `✓/✗/▸/→` glyphs or
  plain-print paths; `shorts.py` guards `stream_summary(camera)["video"]` None (audio-only source →
  loud `SourceError`, not a mid-render `None["width"]` crash); CLI-subprocess error output is
  path-scrubbed before it reaches `receipts.jsonl` (shared `privacy.redact_paths`, reused by the
  bundle); `copy.titles()/description()` fall back to grounded keyphrase copy on a brain hiccup (mirrors
  `chapters()`), so one model failure can't lose the kit; Whisper no-audio / `compute_type` mismatch
  re-raised as plain-language `SourceError`.
- **In-app UX (batch 2):** a **failure modal** (F3) surfaces `errors.friendly_error` in-app
  (`runner.failure_detail` reads the friendly block the subprocess already printed, with a class-name
  fallback via new `friendly_by_name`); an **artifact preview modal** (F4 / `open`) tabs the launch kit
  as text + stubs without a file manager; `open` is honest (shows the path, not a false "opened", when
  there's no OS opener); offline runs leave a clearly-labeled local `placeholder.png` title-card
  (excluded from the A/B pairing). New `tui/screens/failure.py`, `tui/screens/preview.py`.
- **Test debt (batch 3):** fixture-backed `package_run()` e2e (full kit assembly + brain-failure
  survival) and direct `JobManager` + `CliProvider` unit tests — all three had zero prior coverage.
- **Editorial quality (batch 4):** retake candidates carry `pause_before_second_s` (the restart-pause
  retake tell — metadata, candidate set unchanged); the revise loop now feeds the model the **post-cut**
  pacing its last edit produced (`simulate.latest_post_cut_density`) instead of only the pre-cut raw
  density. Golden suite unaffected (it calls `provider.complete` directly, not these paths).
- **CI + distribution (batch 5):** the 3-OS matrix now also runs on path-filtered pushes to `main`
  (catch platform regressions pre-release) with `concurrency` cancel-in-progress; `checkout` v4→v5 and
  `setup-python` v5→v6 off the deprecated Node-20 runtime; `build_wheelhouse.sh` gains `--target`
  (host|linux|windows|macos-arm|macos-x86) so one connected machine stages a correct-arch wheelhouse
  for another OS (verified fetching a manylinux numpy wheel from macOS).
- **Ship:** five commits straight to `main`, tagged **v1.4.0**, `pyproject` 1.3.0→1.4.0. Suite
  581→618 green; coverage 74.0% (floor 67); ruff + mypy clean; fast CI green per batch and the
  matrix-on-main trigger fired live. `vendor/yt_tools/` + the locked eaglet/brand untouched. Human-gate
  items (signing, publish, legal, real-footage dogfood + capped API spend) remain open by design.

## 2026-06-17 — v1.5 "Focus edit" (drag-drop + natural focus brief) — unreleased (lands in the next tag)

A direct request: drag a video into the TUI and say "edit this video: <path> - only focus on my
explanation of X". Two parts, shipped as five trunk commits. **Forking decisions surfaced upfront and
chosen by Lennox:** focus is a soft steer by DEFAULT, with an opt-in **extract** mode auto-armed by
phrasing ("only keep / only focus on / just the part where…"); a focused edit **asks each time** what
to produce; extract is **on by detection**, not a flag.

The grounding truth (verified, not assumed): Eddy is a *compressor*, not a topical extractor. Three
deterministic gates fight "drop the off-topic majority" — `setup_protections` (auto-protects
transition lines, exempt from the budget), `_clip_by_protected` (voids a cut taking >50% of a
protected span), and the loop's length-as-ceiling framing. So a soft prompt hint alone under-delivers
the headline ask; true extraction needs an explicit, isolated relaxation.

- **Parse (batch 1):** `normalize_source` (Finder backslash-escapes / one quote pair / `file://`),
  shlex tokenization so a dropped path with spaces survives, natural lead-ins (`edit`/`extract` verbs,
  bare dropped path → run), and a focus brief = everything after the first ` - `. `is_extract_brief`
  auto-arms `focus_mode` from phrasing. Slash-command guard now excludes absolute paths.
- **Editorial (batch 2):** `EddyMeta.focus`/`focus_mode` (x_eddy-only — no DECISIONS_SCHEMA enum,
  Claire v1.0 / benchmark shapes unchanged); a `USER FOCUS BRIEF` block injected into the initial AND
  revise prompts (carried through compiler-repair via `previous.x_eddy`); the brief is `detect_injection`-
  scanned. **Extract mode** in `compile_with_repair` skips `setup_protections` and raises the
  keep-protection budget to 0.6 — the minimal relaxation that lets the off-topic majority actually drop.
  No target/clamp change needed: the loop already treats length as a ceiling ("being short is fine,
  never restore to pad"), so an extract isn't fought for being short.
- **Plumbing (batch 3):** brief persists in the immutable run manifest (`run_settings`) so `--resume`
  keeps it; threaded CLI (`--focus`, `--extract/--no-extract`, auto-detect; extract defaults to
  video-only) → `jobs.start_run` → `autonomous_run`/`edit_loop` → `initial_decisions`. `RunProfile.focus`
  for a per-channel default.
- **TUI (batch 4):** `OutputScreen` — a focused edit asks Video / +Shorts / Full kit (doubles as the
  confirm); plain runs keep the yes/no confirm.
- **Verified:** dry-run on the real 62-min Codex-call source accepts the file and auto-detects
  `[extract]`, exiting free before transcribe. Suite 618→644 green; coverage 74.5% (floor 67); ruff +
  mypy clean. **Known limit:** the judge isn't yet told about the brief, so it may score an aggressive
  extract below threshold (loop then ships best-effort) — extract quality is model-dependent and only
  provable after a local proxy render. `vendor/yt_tools/` + locked eaglet/brand untouched.

## 2026-06-18 — v1.6 "Extract continuity" (brief-aware judge + bridge-merge) — unreleased

The first live extract run (62-min Codex call → 2.5-min, 21 fragments) proved the v1.5 *targeting* but
exposed *quality*: it correctly isolated the on-topic spans yet shipped 0/3 ship-panel, judge 2.18, gates
failing. Root cause (verified in source): the judge was **brief-blind** — `run_judge`/`evidence_packet`
never read `x_eddy.focus`, so the hostile rubric scored a 4% extract against standalone-video conventions
(hook/completeness/CTA) it structurally can't meet, making the 8.0 threshold mathematically unreachable;
and the compiler had **no gap-bridging**, so 21 slivers survived ("severed mid-thought"). Lennox approved
the **balanced bridge-merge + full pass** (judge + continuity + revision directive + JSON robustness).

- **Brief-aware judge + ship panel** (`qa/judge.py`, `prompts/judge.md`, `loop/controller.py`):
  `_focus_judge_context(focus, focus_mode)` injects an extract/steer block — `boundary_continuity` and
  `pacing` stay strict (a fragmented feel is still a MAJOR boundary defect), but hook/completeness/CTA are
  no longer penalized for an extract legitimately opening mid-context and ending at the topic boundary.
  `run_judge`/`run_ship_panel` gain `focus`/`focus_mode`; the loop passes `decisions.x_eddy.*`. Global
  `judge_threshold` unchanged (the fix is fair scoring, not a lower bar).
- **Deterministic continuity pass** (`edit/compiler.py`, `config.py`, `edit/cutplan.py`):
  `_bridge_keep_gaps` (gated on a new `compile_edl(extract=True)`, so a normal edit is byte-identical)
  bridges consecutive keeps whose gap ≤ `extract_bridge_gap_s` (6s) into one contiguous block, snaps
  edges OUT to phrase boundaries within `extract_phrase_snap_window_s` (1.5s), and drops orphan blocks
  below `extract_min_block_s` (2.5s). Re-admitting a ≤6s bridge can't violate `protected_moments` (it only
  ADDS kept content). The "aggressive" variant is now a config change, not code.
- **Extract-aware revision directive** (`loop/controller.py`): `_directive_from(focus_mode=…)` — in extract
  mode the over-ceiling compression escalation is skipped (no ceiling race) and only continuity-restoring
  judge fixes (`restore`/`extend_pad`/`tighten_gap`) pass through; **never `drop_beat`** (that caused the
  v1.5 iter-2 thrash that grew the cut and severed more explanations).
- **Long-source JSON robustness** (`providers/base.py`, `providers/ollama.py`): `extract_json` is now
  string/escape-aware and, on a truncated object (a long cut list overrunning `num_predict` — the v1.5
  crash), salvages the complete elements and re-validates, falling through to the original error if the
  salvage won't parse (no silent corruption). Ollama grows `num_ctx` adaptively toward `num_ctx_max`
  (49152) when the estimated prompt is large; short prompts stay at the 32768 default.
- **Verified:** full suite green; ruff + mypy clean; new `test_continuity_pass.py` + extended
  `test_focus_edit.py`/`test_model_boundary.py` (bridge geometry, phrase-snap, JSON-repair, brief-aware
  judge, extract directive). Live 62-min re-run pending. `vendor/yt_tools/` + locked eaglet/brand untouched.

## 2026-06-18 — v1.6.1: live-run fixes (the re-run exposed three of my own regressions)

The v1.6 62-min re-run **validated the headline fix** — the brief-aware judge scored the extract
**5.73–6.91** (vs 2.18 brief-blind) and bridge-merge cut 21 fragments to 7 blocks — but it also
regressed three ways, all traceable to v1.6 changes, and shipped a 17.4-min over-ceiling cut in 222
minutes. Honest post-mortem + fixes:

- **Adaptive `num_ctx` was net-negative** → DISABLED by default (`num_ctx_max` 49152 → **0**).
  Bumping the local 27B to a 49152 window made editorial calls 7–16× slower (one `revise` took **50
  min**; total 222 min vs 31). The string-aware `extract_json` salvage already covers the truncation
  risk it was added for, so the grow is now opt-in only.
- **Extract directive removed the loop's only length lever** → made **ceiling-aware**. The local model
  is non-deterministic (2.5 min one run, **17 min** the next on the same prompt); the v1.6 "continuity-
  only, never drop_beat" branch left an over-cut extract with no way to shrink, so it grew unboundedly
  and thrashed 6 iterations. Now the continuity-only short-circuit fires ONLY while **under** the
  ceiling; an over-ceiling extract falls through to normal compression.
- **Bridge-merge re-admitted silence** → **speech-gated**. Setting `prev.end = r.end` across a *silent*
  gap replayed removed silence and failed the dead-air gate (`dead_air` 10 → **0**; ship panel: "DRAGS
  ≈200s"). A gap is now bridged only when it contains removed SPEECH (a phrase overlaps it); a silent
  gap stays a clean splice.
- **Verified:** suite 665→668 green, coverage 75.0% (floor 67), ruff + mypy clean. Second 62-min
  re-run pending with all three fixes.
