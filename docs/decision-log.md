# Decision Log

Durable product/architecture decisions. Newest first. Format: date · decision · why.

## 2026-06-23 — Public Eddy repo + unattended gate-passing editor

1. **Repo identity:** `/Users/lennoxsaint/eddy` is the canonical public MIT Eddy editor repo.
2. **Install surface:** root `SKILL.md` + `scripts/install_agent_skill.py` let Codex/Claude install Eddy from a GitHub link.
3. **Loop policy:** Eddy must keep repairing and rerendering until deterministic gates pass, stopping only for impossible blockers with exact receipts.
4. **Studio Sound:** Eddy's default Studio Sound is local studio-mic cleanup: denoise where available, mouth-click cleanup where available, speech EQ, compression/limiting, and loudness normalization. Exact Descript Studio Sound is optional only when a Descript workflow is explicitly chosen.
5. **Long layout:** separate screen + camera sources render with stable screen continuity and a bottom-right rounded camera square.
6. **Shorts:** target five Shorts, but output fewer when fewer standalone segments pass editorial and deterministic QA.
7. **Publishing boundary:** no video upload, publish, schedule, or send actions are part of Eddy.

## 2026-06-11 — Full grilling completed, v1 locked (Claude Code session)

1. **Scope: full launch kit.** Drop footage in → thumbnails + title + edited long + shorts w/ karaoke captions + chapters/description. No publishing.
2. **Loop priority: cut quality first.** Polish only after structure converges.
3. **Approval: after final render.** Fully autonomous run; Lennox reviews the finished kit.
4. **Brain: local-only default (Ollama qwen3.6-27b).** Core promise = free unlimited editing. Five providers ship working: Ollama, Anthropic API, OpenAI API, codex CLI (ChatGPT subscription), claude CLI (Claude subscription).
5. **Architecture: standalone engine** in this repo; the proven reference tooling vendored as the base (`vendor/yt_tools/`, never edited). No Descript, no Chrome MCP, no agent-session coupling.
6. **Transcription: faster-whisper local**, word-level, cached by source hash.
7. **Thumbnails: Gemini + OpenAI images** — the only paid path, cost-logged, skip-with-receipt without keys.
8. **Onboarding: `eddy doctor`** — hardware + credential detection → tier recommendation → config write.
9. **Original done gate:** deterministic QA + judge >=8/10 with bounded iterations. Superseded by the 2026-06-23 loop-until-pass decision above.
10. **Input: camera+screen+mic or single composite** — degraded (no-screen) layout is the primary path.
11. **Two-artifact contract:** model emits Claire-schema remove-list `edit-decisions.json`; deterministic compiler emits video-use-schema `edl.json`. Converter to prior-pipeline benchmark format for objective diffs.
12. **Judge is text-only** — boundary splice cards + stats, defect-list-first, consistency-checked; demotes to advisory if unstable at q4.
13. **Build tracked live on Linear** team EDD, project "Eddy v1", tiny sequenced issues.
14. **Ship-readiness in v1:** pipx-installable, no personal hardcoded paths, stranger-readable quickstart. Superseded by the 2026-06-23 public MIT repo decision above.

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
- **EDD-84 — documented, not silently closed:** EDD-84 is an external Linear (team EDD) tracking item from the production-readiness audit. Its exact body was not reconcilable inside this offline build (no verified Linear access this session), so it is explicitly **carried into the later reconciliation batch**: when Linear access is available, reconcile EDD-84 (and the rest of team EDD) against the actually-shipped v0.4→v1.0 work recorded in `BUILD-STATE.md` and the git tags. It is referenced as an open item in `docs/KNOWN-LIMITS.md`. No claim is made here that EDD-84's specific defect was fixed — only that it is tracked and routed to reconciliation.
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

## 2026-06-18 — v1.6.2: schema tolerance (the second re-run crashed on a truncated cutplan)

The v1.6.1 re-run crashed at iteration 1: `ollama failed after retry: missing required key
'protected_moments'`. Cause: at the fast 32768 window the model emitted a huge cut list that hit the
12288 `num_predict` cap and truncated after `cuts`; the v1.6 `extract_json` salvage correctly recovered
`{retakes, cuts}`, but `DECISIONS_SCHEMA` marked all four arrays **required**, so the salvage (and the
retry) were rejected. Fix: `DECISIONS_SCHEMA.required` → **`["cuts"]`** only. `retakes`,
`protected_moments`, and `shorts_candidates` all default to `[]` in `EditDecisions`, so a model that
omits one — or a truncated-then-salvaged response — now validates and lets pydantic fill the empties
instead of aborting the run. This is general robustness (not extract-specific). Kept `num_ctx` at the
fast default: the truncation was a `num_predict` ceiling, not a context overrun, so a bigger (slower)
window wouldn't have helped. Suite 668→670 green, coverage 75.0%, ruff + mypy clean. Re-run pending.

## 2026-06-18 — v1.6.3: remove-level bridging + the two "next steps", honestly

Lennox asked to execute the two recommended next steps. One shipped; one is blocked on this machine:

- **Step #1 (bridge-then-retighten) — SHIPPED.** Moved extract gap-bridging from a post-inversion
  EdlRange merge to the REMOVE level: drop the small CUT spans (≤ `extract_bridge_gap_s`) that chop one
  explanation into slivers BEFORE silence removal, so the on-topic keeps join and `silence_cut_intervals`
  still cleans the silence inside a re-admitted bridge. Fixes two flaws of the post-inversion merge: it
  replayed silence (dead-air gate) and couldn't tell a retake from a cut. `_bridge_keep_gaps` →
  `_finalize_extract_blocks` (phrase-snap + sliver-drop only). Tests at `compile_edl` level: small cut
  bridged, large off-topic cut kept, retake preserved, normal edit byte-identical.
  **Honest validation:** a fresh 62-min local re-run stayed crash-free, $0, under ceiling, `dead_air`
  10/10 — but landed at **49 blocks / 4.9 min** (judge 6.09), NOT fewer than the prior 19. Cause: the
  local model is non-deterministic (this draw kept ~2× the content), and on a pause-heavy screen-share
  demo the block count is dominated by **silence cuts at demo pauses**, which bridging deliberately does
  not touch (to keep audio clean). The bridge is architecturally correct but its "fewer blocks" win is
  swamped by silence-driven fragmentation on this source. The real remaining lever is a taste tradeoff:
  raise the extract silence-cut threshold (`silence_min_cut_s` ~0.4→~1.0s) so natural sub-second demo
  pauses are KEPT (contiguous) rather than cut (many clean-but-choppy splices). Not auto-applied.
- **Step #2 (stronger editorial brain) — SKIPPED (Lennox's call).** Every clean cloud path is blocked
  here: `claude_cli` inherits the global CLAUDE.md and refuses/prose-wraps the cut-JSON; `codex_cli`
  won't start (`config.toml` `service_tier` invalid); no `ANTHROPIC_API_KEY` in env; only paid `openai`
  gpt-5.1-mini works (metered + "mini", crosses the no-paid-API rule). The local qwen36-27b-codex is
  purpose-fit for structured cut-JSON; Lennox chose to keep the $0 local pipeline.

Suite green (670), coverage 75.0%, ruff + mypy clean. `vendor/yt_tools/` + locked brand untouched.

## 2026-06-18 — v1.6.4: extract silence-threshold tweak — tried, did NOT cleanly help

The remaining lever from v1.6.3: an extract now KEEPS natural sub-second pauses (`extract_silence_min_cut_s`
1.0 vs 0.40 normal) instead of cutting every ≥0.4s gap, with a matching output-silence gate tolerance
(`extract_max_output_silence_s` 1.2) threaded through `run_deterministic`. Deterministically verified
(a 0.7s pause is cut by a normal edit, kept by an extract). **Honest live result:** a fresh 62-min draw
landed at 43 blocks / 11.3 min, judge 6.0 (continuity 4, pacing 3), and the `dead_air` quality signal
dropped 10 → 6.67 — i.e. keeping pauses added perceptible dead air with NO clear block-count or judge
win. The deeper finding across five live runs: the local model's NON-DETERMINISM dominates everything —
the same prompt kept 2.6 / 4.9 / 11.3 min on different draws, so duration, block count, and judge swing
far more run-to-run than any deterministic post-processing tweak moves them, and a 62-min rambling demo
has inherent long silent screen-share stretches no cut threshold cleanly resolves. The one clearly
VALIDATED win remains the brief-aware judge (2.18 → 5.7–6.9). The silence tweak is sound + config-gated
but a marginal tradeoff; left in as an option pending Lennox's call (keep / soften to ~0.7 / revert).
Suite 669 green, coverage 75.1%, ruff + mypy clean.

**REVERTED (`8473fa8`):** Lennox's call — the tweak added dead air for no measurable win, so it's out;
the extract silence floor is back to the tested-clean 0.40s / 0.60s gate. The honest standing
conclusion: deterministic post-processing has hit the local-model-variance wall. The validated win
(brief-aware judge) stays; the real next lever for splice quality is a more deterministic/stronger
editorial brain, not more tuning. Suite 668 green, coverage 75.0%, ruff + mypy clean.

---

## v1.7 — best-of-N self-consistency for the extract brain (/goal: stronger, lower-variance editorial brain)

**The bar (5-draw $0 local extract baseline, single draft, temp 0.3, cached transcript):**
clean-ship **0/5**; judge mean 6.07 / **stdev 1.154** (4.27–7.82); quality 7.376/0.658; blocks mean
27.2 / **stdev 28.9** (5→82); dur 6.75min / stdev 5.56 (2.29→17.22). Draws 33–90 min each.

**Non-determinism quantified (micro-harness, 9 iter-1 drafts, render-free):** the SAME prompt gives
blocks 6→151 and dur 26s→45min. objective barely varies (8.1–9.1) and does NOT correlate with judge
(the 9.1-objective draft scored judge 5.18). The brain is the variance source — the /goal thesis.

**best-of-N (WIRED, opt-in `loop.ensemble_n`, default 1=OFF, EXTRACT-gated):** sample N iter-1 drafts,
pick the winner by a deterministic render-free selector (feasibility band → objective → fewest blocks).
Micro-harness best-of-3 vs single: blocks **stdev 59→5.3** (11× tighter), the catastrophic over-ceiling
drafts (130–151 blocks / 35–45min) ELIMINATED, judge floor 5.64→5.88. This is a real, proven win on the
STRUCTURAL determinism the brain controls. (`src/eddy/edit/ensemble.py`, `controller.py:293`, 8 tests.)
NOT a win on judge variance (0.92→0.80): the objective selector doesn't track judge, and the judge is
itself a noisy LLM — a partly-irreducible floor on judge stdev.

**Clean-ship blocker is NOT the brain (key finding):** every draw fails the deterministic `no_dead_air`
(2–3s spans) / `silent_motion` (32–102 spans >0.6s) gates. Root cause (verified on d5): `audio-silence.json`
(energy, −34dB) flags regions as silent that Whisper transcribed as WORDS (quiet/trailing speech); the
compiler correctly won't cut word-overlapping spans (never clip speech), so those survive. An
audio-vs-transcript disagreement, not a bug — resolving it means risky speech-clipping or silence-threshold
retuning (the v1.6.4 territory already reverted). A trim-instead-of-skip fix was tried and REVERTED
(silent_motion 32→25, dead-air unchanged — barely helped, unproven hot-path change). Judge ceiling ~7.8<8.0
(bad_splice + drag defects).

**Honest conclusion:** the STRICT ship gate (gates pass AND judge≥8 in ≥4/5) is unreachable via the
editorial brain alone on this rambling 62-min source — blocked by an orthogonal compiler/audio dead-air
issue + a judge ceiling, exactly the /goal ceiling note's scenario. best-of-N delivers the genuine in-scope
brain win (structural determinism). Per the ceiling note, relaxing criterion #2/#3 to "beats baseline floor
+ variance" needs Lennox's explicit approval — surfaced. Suite 676 green, cov 75.1%, ruff + mypy clean.

### v1.7 confirmation (full 5-draw runs, $0 local) — RESULT

| metric | baseline (n=1) | best-of-3 | best-of-5 | N=5 vs baseline |
|---|---|---|---|---|
| judge stdev | 1.154 | 0.755 | **0.339** | **↓71%** |
| quality stdev | 0.658 | 0.418 | **0.270** | ↓59% |
| blocks stdev | 28.9 | 31.4 | 26.4 | ↓9% |
| dur stdev (min) | 5.56 | 8.08 | 4.97 | ↓11% |
| over-ceiling catastrophes | 1 | 1 | **0** | eliminated |
| judge mean | 6.07 | 5.91 | 6.18 | floor +0.11 |
| clean-ship | 0/5 | 0/5 | 0/5 | (dead-air gate + judge ceiling) |

**Verdict:** best-of-N (N=5 + contiguity-first selector) is a DECISIVE win on the brain-controlled
determinism — judge stdev ↓71% (1.154→0.339, well past the criterion-#3 "≤ half" = 0.577 bar), quality
stdev ↓59%, over-ceiling catastrophes eliminated. The N=3 run was mixed because (a) the selector ranked
objective above blocks [fixed `ba67f72`] and (b) ~45% of single draws are catastrophes so 0.45^3≈9% of
groups were all-bad; N=5 (0.45^5≈1.8%) closed it.

**Residual (honest, documented future work):** block-count stdev only ↓9%. Two deeper causes, NOT the
ensemble: (1) BAD GROUPS — confirm2-d2's 5 drafts were all over-ceiling/degenerate/bloated, so the pick
was a degenerate 1-block/3.2s extract; (2) REVISE-LOOP BLOAT — confirm2-d5's ensemble picked a tight
8-block/55s draft at iter-1 but the revise loop grew it to 75 blocks by iter-5 (best() ranks by quality,
which favors more content). Fixing these = a degenerate-tiny selector guard + an extract-aware best()/
revise that won't re-bloat a tight pick.

**Unchanged ceiling (NON-brain):** clean-ship 0/5 — blocked by the deterministic dead-air/silent-motion
gates (audio-energy −34dB flags quiet/trailing speech that Whisper labeled as words → un-cuttable without
clipping speech) + a judge ceiling ~7.8<8.0. Confirmed the prior session's conclusion: the real next lever
is a STRONGER / more-deterministic MODEL, not more local post-processing. Recommended extract setting:
`loop.ensemble_n = 5`. Strict criterion #2/#3 relaxed to this determinism win WITH Lennox's approval.

### v1.7 criterion #4 — no normal-edit regression + held-out (not overfit)

**4a normal-edit regression (PASS):** a NORMAL `eddy run` (dev-greatest-hits, NON-extract) with
ensemble_n=5 produced a valid edit (5 ranges, 1.7min) with **0 ensemble receipts** — the gate
(`ensemble_n>1 AND focus_mode=="extract"`) correctly leaves non-extract edits on the single-draft path,
byte-identical to pre-v1.7. (The crit4.sh PASS/FAIL print mis-fired on a `grep -c ... || echo 0`
double-output bash bug; the real ensemble count is 0.)

**4b held-out source (PASS, not overfit):** micro-harness on a DIFFERENT 54-min source (the Fable 5
review), n=10 extract drafts. Non-determinism generalizes — single-draft judge stdev 0.824, blocks 6–20,
dur 11–38min. best-of-5 reduces it on the held-out too: judge stdev 0.824→**0.635**, blocks stdev
4.58→**2.0**, picked blocks mean 16.2→8. Directional (2 ensemble samples; editorial-level not full-run)
but consistent with the Codex full-run win — the determinism gain is NOT overfit to one source.

**Final criteria status:** #1 ✅ baseline, #2 ❌ clean-ship 0/5 (structurally unreachable — NON-brain
dead-air gate + judge ceiling; relaxed WITH Lennox's approval), #3 ✅ judge stdev 0.339 ≤ 0.577,
#4 ✅ no normal regression + not overfit, #5 ✅ suite 676 green / cov 75.1% / ruff + mypy clean.

## 2026-06-22 — v1.7.3: honor a runtime stated in the focus brief + the stale-install root cause

**Trigger.** Lennox ran his footage with the brief "make it focus on my 5-10 minute explanation of
what Codex is" and it did not produce a focused 5-10 min extract.

**Root cause (verified, two layers):**
1. **Dominant — stale install.** The `eddy` on PATH is a **pipx** install (`~/.local/bin/eddy` →
   `~/.local/pipx/venvs/eddy`) frozen at **v1.4.0**, built from `/Users/lennoxsaint/eddy[mcp]` back
   when the repo was v1.4.0. Its `eddy run --help` has **no `--focus`/`--extract`** — the entire
   focus/extract feature (v1.5), brief-aware judge + continuity (v1.6), and best-of-5 (v1.7) live only
   in the working tree and were never reinstalled. So the live binary literally cannot do a topical
   extract. (The interactive TUI he launched, PID 65849, is that v1.4.0.) Fix: reinstall the pipx
   `eddy` **editable** from the repo so the binary == HEAD and never drifts again.
2. **Real gap even on HEAD — the stated duration was ignored.** `target_s = default_target_minutes*60`
   (12 min) and the default ceiling is 14 min; the "5-10 minute" in the brief was never parsed. So even
   after a reinstall, the requested length wouldn't be honored.

**Decision.** Parse an explicit runtime out of the focus brief and use it as the loop target + length
ceiling. New `duration_from_brief()` in `tui/intents.py`: a RANGE ("5-10 min") targets the top and caps
there; a capped single ("under 8 min") targets a touch below the cap; a plain single ("a 10 min cut")
targets that with small ceiling slack; sane band 15s–3h else None. Wired in `cli.run()` **only** when no
explicit `--target-minutes` and the default format (a named format deliberately raises/disables the
ceiling, so it's never overridden). Explicit flags always win.

**Verified.** 16 new unit/CLI tests (range/word-`to`/reversed, capped single, hours, seconds, the
top-5/year/version non-durations, overlong reject; CLI: band→target+ceiling, `--target-minutes` wins,
named format preserved). Full suite **692 passed** / 5 skipped, cov 75.34%, ruff + mypy clean.
**Not verified:** no full $0 render this turn — the end-to-end "lands at 5-10 min" claim rests on the
target+ceiling now being correct, not on a re-render. Known follow-up: the best-of-N selector ranks
`over_ceiling_s` against the **config** ceiling, not the per-run brief ceiling — first-draft selection
won't yet prefer ≤10 min, though the revise loop + ship gate still enforce the run ceiling.

## 2026-06-22 — v1.7.4: simpler chooser + honest per-run progress (TUI)

**Trigger.** Two live-run screenshots: (1) the "What should Eddy make?" chooser had a 4th button
clipped off the right edge — Lennox couldn't read it; (2) progress always said "step 1 of 10" even
though a "just the video" run skips Shorts + Titles.

**Root causes.** (1) `OutputScreen` rendered four buttons (`Video / + Shorts / Full kit / Cancel`) in a
fixed 64-col dialog with per-button margins and no width cap → Cancel overflowed. The choice keys were
also shown 3× (inline text, buttons, footer). (2) `tui/phases.py` hardcoded a 10-stage `_ORDER`, so the
total and the step index counted stages that wouldn't run; a run-start banner hardcoded to
`EDDY · editing` (printed once, captured in the TUI log tail) also contradicted the live phase.

**Decisions (Lennox-approved).**
- Chooser: **drop the Cancel button** (3 buttons never clip); `esc` and a **click on the backdrop**
  both cancel (new `on_click` → `dismiss(None)`). The triple key-hint collapses to one line describing
  what each output produces (`Video = the edited long · + Shorts adds clips · Full kit = titles…`).
- Progress: the engine records the **actual ordered stages this run will run** (`_run_plan` mirrors the
  same skip-flag/config conditionals that gate `set_phase`) into `state.json` (`RunState.set_plan`); the
  monitor renders a **stage breadcrumb** (`✓ done · ▸ current · dim pending`) + an honest "step k of N"
  via `phases.breadcrumb`/plan-aware `phases.progress`. The variable-length edit loop stays one
  "Editing" step but shows the live "(pass N)". Banner subtitle changed `editing` → neutral `starting`.
- `phases.py` stays Textual-free; the engine imports nothing from the TUI (the plan is a `list[str]` of
  phase keys the engine already owns — the TUI only renders it). Older runs / a direct `edit_loop`
  fall back to the static full order.

**Verified.** New tests: `test_tui_output.py` (3 buttons, no `#cancel`, esc + backdrop-click cancel,
flags intact), `test_tui_phases.py` (per-run `progress` "of 5/6/4" vs static "of 10", breadcrumb
markers), `test_run_plan.py` (video-only omits shorts+package; flags toggle optional stages). Live
render check: a default video-only run = **6 stages** (studio_sound on), not 10. Full suite **704
passed** / 5 skipped, cov 75.29%, ruff + mypy clean. **Not verified:** no full TUI run rendered to
completion this turn — the rendering claims rest on the unit coverage above + a static render check.

## 2026-06-24 — v1.8.1: Codex Club public-readiness hardening

**Trigger.** The public `main` branch was visible but not share-ready for Codex Club: both GitHub
Actions workflows failed before tests, the MCP install docs pointed at the occupied public PyPI
package name, and public-scrub skipped vendored reference scripts that still contained private
machine paths.

**Decisions.**
- Keep Eddy at Python **3.11+** for creator accessibility, but constrain dev/CI NumPy below the stub
  syntax break that requires a Python 3.12 mypy target.
- Treat GitHub-source installs as the only public install path until Eddy owns an index package name:
  `pipx install "eddy[mcp] @ git+https://github.com/lennoxsaint/eddy.git@v1.8.1"`.
- Keep the golden local-model suite as a maintainer-local release proof, not something GitHub CI
  silently implies.
- Sanitize `vendor/yt_tools/` public copies despite the usual vendor-read-only guard because the
  approved readiness plan explicitly required removing private absolute paths before sharing.
- Label the baked Shorts hook corpus as metadata-derived when it comes from public YouTube metadata,
  not transcript-proven Supadata hooks.

**Expected proof before sharing.** `ruff check src tests`, `mypy src/eddy`, full `pytest --cov`,
`scripts/public_scrub_check.py`, a clean GitHub-source install smoke, both GitHub Actions workflows
green, and a fresh `v1.8.1` tag only after those gates pass.

## 2026-06-25 — One-sentence install promise becomes `eddy edit`

**Trigger.** Lennox's Codex Club sharing bar is not "install a repo and learn an internal CLI." It is:
give an agent the Eddy GitHub URL, attach raw footage, say "edit this," and receive either a finished
local YouTube edit/Shorts package or exact blockers with proof. The repo already had most building
blocks, but the public agent path still taught `eddy run`, the MCP server exposed only lower-level
job starters, and the baked Shorts hook corpus lived in repo docs rather than package data.

**Decisions.**
- Add `eddy edit` as the promise-level wrapper. It opens a source-locked run, discovers media, runs
  preflight, selects a template, routes the editorial brain, verifies the hook corpus and motion
  prerequisites, then either delegates to the existing autonomous pipeline or writes
  `one-sentence-state.json` plus `support-bundle.zip`.
- Keep `eddy run` as the lower-level escape hatch for profiles, topical extract mode, and manual
  skip flags.
- Expose the same promise path to agents through MCP as `eddy_edit_start`; Claude Code plugin docs and
  commands now start there.
- Make capability routing deterministic over `doctor.detect()` output. Environment probing happens in
  `detect()`, not hidden inside the router, so tests and support bundles do not inherit the maintainer's
  shell credentials by accident.
- Ship the 1,000-record hook playbook as package data under `eddy/references/` as well as the repo
  documentation copy under `docs/references/`.
- Add `eddy bootstrap` as a plain-English repair plan for preflight blockers.

**Proof target before broad sharing.** Focused tests cover template selection, routing, exact-blocker
support bundles, MCP `eddy_edit_start`, and root skill install wording; full repo gates still need to
run before this is considered share-ready.
