# Eddy GA Autonomous Build — `/goal` + `/loop` state

Live ledger for the v0.4→v1.0 march. Source of truth for "where are we" across context
compaction. Plan: `~/.claude/plans/019ead42-117d-7aa3-a28c-d8aa5ab1e87b-gri-sorted-island.md`.

## `/goal` — north star + acceptance

**GOAL:** Take Eddy from v0.3.2 to production-grade GA (v1.0): all 6 milestones implemented,
each ff-merged to `master` **locally** and tagged, full suite + fixture e2e + golden suite green,
product claims honest, human-gate batch documented.

**DONE when ALL true:**
- Milestones v0.4…v1.0 merged to `master`; tags `v0.4`…`v1.0` exist.
- `pytest` full suite green; coverage floor met; `ruff` + `mypy` clean.
- Fixture-backed `eddy run` e2e green; golden editorial suite green vs the **pinned qwen q4**.
- Claims match behavior: no network egress without logged opt-in; `--local-only`/`EDDY_OFFLINE` works;
  README/PRIVACY accurate.
- Human-gate batch (below) written here and surfaced to Lennox.
- No item ever marked done without its verification gate green.

## `/loop` — continuation, gate, stop

**CONTINUE** the loop while ALL hold:
- an unblocked build item is not yet Done, AND
- the full suite is green (the last item/milestone did not regress), AND
- no unrecoverable blocker is open, AND
- remaining work is not entirely human-gate-blocked.

**Each iteration:**
1. Pick the next unblocked item by dependency order — **foundation → bug-fix wave → features**,
   finishing the current milestone before advancing.
2. Implement (direct edits in the main agent; `Workflow` fan-out only for genuinely independent
   batches, e.g. the v0.5 test-writing sweep).
3. **VERIFY GATE (hard):** targeted tests pass **AND** full suite stays green (test count never
   decreases) **AND** render/e2e items also pass the synthetic-fixture e2e.
4. Commit on the milestone branch; update this ledger; flip Linear EDD if reachable.
5. On milestone `exit_criteria` met + a `code-reviewer` adversarial pass: ff-merge to `master`,
   tag, `pipx` reinstall global `eddy`, write a milestone report + **Second Brain log**.

**STOP / pause** when ANY:
- All milestones complete → present the human-gate batch; declare **GA-ready-pending-gate**.
- A verification gate fails and isn't green after **2 self-fix attempts** → stop, write a diagnosis,
  escalate.
- Remaining work is human-gate-blocked (money / credentials / signing / publish / non-Mac hardware)
  → stop, present the batch.
- A change would touch a forbidden surface → stop, ask.

**PACING:** self-paced via `ScheduleWakeup` between batches; no fixed clock.

**INVARIANTS (every iteration):** never mark done on assertion alone · never push · never publish ·
never touch `vendor/yt_tools/` · never mutate source video · **no real-API spend before the gate**
(local qwen + cached transcript only during the march).

## Milestone ledger

| Milestone | Branch | Status |
|-----------|--------|--------|
| v0.4 stabilize | `v0.4-stabilize` | **DONE** — merged to master, tagged `v0.4` (suite 100→163, ruff+mypy clean, code-review SHIP-WITH-NITS) |
| v0.5 robustness | `v0.5-robustness` | **DONE** — merged to master, tagged `v0.5` (suite 163→335 +golden; review SHIP-WITH-NITS, all nits cleared) |
| v0.6 crossplatform | `v0.6-crossplatform` | **CODE DONE** — 9/9 autonomous items merged to master, tagged `v0.6` (review SHIP-WITH-NITS, fixed). Distribution VALIDATION (3-OS CI green, signed installer, publish) is 🔒 human-gate-blocked. |
| v0.7 operability | `v0.7-operability` | **DONE** — 10/10 merged to master, tagged `v0.7` (review FIX-BEFORE-MERGE: 2 criticals + 2 important all fixed, re-verified). Note: corrective-control re-edit + NSFW-model moderation deferred (bigger/needs-API). |
| v0.8 breadth | `v0.8-breadth` | **DONE** — 9/9 autonomous items merged to master, tagged `v0.8`, v0.8.0 pipx-installed (suite 405→439, ruff+mypy clean; review NO-CRITICAL: 2 important [EDL speed drift, profile bool precedence] + 2 nits all fixed). |
| v1.0 GA | `v1.0-ga` | **DONE** — 8/8 autonomous items merged to master, tagged `v1.0`, v1.0.0 pipx-installed (suite 439→464, cov 69.0%, golden GA gate GREEN on the real pinned qwen:q4 in 16s; review NO-CRITICAL-after-fix: 1 critical [offline egress leak via CLI-subprocess brain] + 2 important + 4 nits all fixed). Signing/notarize/publish + 3-OS CI green remain 🔒 human-gate. |

### v0.4 items
- [x] **Model boundary** — reject non-finite timestamps at JSON/schema/compiler (`1283f5a`, +13 tests)
- [x] **Atomic state/EDL writes + tolerant loaders** — `atomicio.py`, RunState/receipts tolerant (+6 tests)
- [x] **`validate_against` recursive** (nested required + types + enums) (`base.py`, +8 tests)
- [x] **Judge clamp to 1–10 + `.get()` defect keys + in-try processing** (`judge.py`, +7 tests)
- [x] **Path-containment gate `is_relative_to` over all outputs** (excl. `-i` inputs) (`ffmpeg.py`, +6 tests)
- [x] **Slug re-hash (wrong-footage guard) + wire `--resume`** (`runs.py`, +5 tests)
- [x] **Apostrophe concat — shared `concat_quote` helper** (`ffmpeg.py`; segments+shorts) (+ tests above)
- [x] **Interrupt-safe segment render (.partial + os.replace)** — kills the truncated-segment-reuse hazard (`segments.py`, +1 test). (ffmpeg children already die with the process group on Ctrl-C; full post-loop phase idempotency deferred to a v0.4.x follow-up — resume re-running post-loop phases is wasteful, not incorrect, now that segments are atomic+cached.)
- [x] **Model-call + wall-clock budget** (cumulative, iteration-head, ships best-effort) (`config.py`/`controller.py`, +4 tests)
- [x] **Git-derived version + `eddy --version` + receipt stamp** (`__init__.py`/`cli.py`/`runs.py`, +3 tests)
- [x] **Privacy honesty: `--local-only`/`EDDY_OFFLINE` + `local_files_only` + egress disclosure + PRIVACY.md/README** (`privacy.py`+5 files, +4 tests) — interactive one-time consent prompt deferred to v0.7 onboarding (logged egress disclosure is the v0.4 floor)
- [x] **CI workflow (ruff+mypy+pytest+cov)** + made the codebase ruff/mypy clean (`.github/workflows/ci.yml`)
- [x] **Pin/record editorial model per run + drift warning** (`controller.py`, +4 tests)
- [x] **Legal drafts (LICENSE + EULA.md + AUP.md + THIRD-PARTY-NOTICES.md)** — DRAFTs for your + lawyer review → human-gate #1

### v0.8 items (breadth — all autonomous-able)
- [x] **Editor-native timeline export** (`final/timeline.edl` CMX3600 — import into Premiere/Resolve/FCP) (`nle_export.py`/`launch_kit.py`, +3 tests)
- [x] **Batch/queue runner + `eddy runs`** (`eddy batch <root>` — many sources, per-item failure recovery, `--json` headless + nonzero exit on failures) (`batch.py`/`cli.py`, +4 tests)
- [x] **Named per-channel profiles / `--profile`** (config `[profiles.<name>]` → target_minutes/format/language/skip_shorts/skip_package run defaults; `eddy run --profile <name>` with explicit-flag-wins precedence; unknown profile = hard error; `eddy profiles` lists them) (`config.py`/`cli.py`, +5 tests)
- [x] **Format profiles** (`eddy run --format tutorial|lesson|longform|podcast` raises the ceiling so the loop doesn't compress step-by-step content) (`formats.py`/`controller.py`/`cli.py`, +3 tests)
- [x] **Audio-first ingest** (.wav/.mp3/.m4a/.flac/.aac… accepted so podcasters can `eddy transcribe`; `eddy run` on audio fails loud with a `eddy transcribe` hint, not a cryptic "no video stream") (`runs.py`, +4 tests)
- [x] **Standalone `eddy shorts <source>`** (`mine_shorts`: transcribe -> ONE decision pass -> render shorts only, no iterative loop / no long render; `shorts` command now dual-mode: existing run dir = render stage, raw footage = standalone mine) (`controller.py`/`cli.py`, +1 orchestration test)
- [x] **A/B title/thumbnail pick (`eddy pick`) + decision-template reuse** (deterministic `TITLE_AB_RUBRIC` = the reusable decision template: scores title-craft signals, picks A=best + B=highest-scoring *divergent* candidate, flags weak tests honestly; thumbnails paired by file w/ no-vision disclaimer; persists `titles.json` + writes `ab-pick.json`/`AB-TEST.md`; wired into packaging + standalone `eddy pick <run_dir>`) (`package/abpick.py`/`launch_kit.py`/`cli.py`, +7 tests)
- [x] **Multi-speaker/interview detection + warning** (heuristic over transcript cues + pause density, conservative/under-warns, low|medium confidence, never authoritative; non-blocking warning after transcribe in `autonomous_run` + `mine_shorts`; per-speaker editing stays out of scope) (`edit/speakers.py`/`controller.py`, +4 tests)
- [x] **RTL/CJK caption guard** (burned word-captions do no bidi/shaping; detect RTL/CJK script in caption text and warn once — pointing at the v0.7 sidecar .srt/.vtt — instead of silently shipping reversed/tofu captions) (`render/scripts.py`/`render/captions.py`, +5 tests)

### v1.0 items (GA hardening — autonomous; signing/notarize/publish are human-gate)
- [x] **Verifiable no-egress + active egress guard** (`--local-only`/`EDDY_OFFLINE` now ENFORCED at the syscall boundary: non-loopback TCP connects raise `EgressBlocked`; loopback/Ollama allowed; hermetic test proves resolving the offline brain attempts zero egress) (`netguard.py`/`cli.py`, +7 tests)
- [x] **Coverage floor (ratchet) + required-green-before-tag** (`[tool.coverage.report] fail_under=68` in pyproject; CI `pytest --cov=eddy` fails under it; current 68.8%; +2 cheap pure-logic tests) (`pyproject.toml`/`ci.yml`/`tests/test_render_long.py`)
- [x] **Offline wheelhouse builder + airgap docs** (`scripts/build_wheelhouse.sh` downloads the pinned dep closure + builds the eddy wheel for `pip install --no-index`; `docs/AIRGAP.md` covers wheelhouse + ffmpeg + Whisper cache + Ollama model staging + the enforced egress guard) (+4 guard tests)
- [x] **Reproducibility proof** (two-tier model documented in `docs/REPRODUCIBILITY.md`: deterministic core is byte-reproducible; local qwen gains an EXACT mode via new `[provider.ollama] seed` → `options.seed` at temperature 0; golden suite gates quality mode) (`config.py`/`providers/ollama.py`, +4 tests incl. byte-identical EDL recompile)
- [x] **Release process** (`docs/RELEASE.md`: required-green gate [ruff+mypy+cov-floor+golden+matrix], local tag/pipx flow, signing/notarize [human-gate], update + rollback)
- [x] **Support runbook + known-limits** (`docs/SUPPORT.md` triage: doctor→dry-run→bundle + symptom table; `docs/KNOWN-LIMITS.md` honest scope boundaries) (+4 doc tests)
- [x] **EDD-84 disposition documented** (`docs/decision-log.md`: this build used BUILD-STATE.md not Linear; EDD-84 routed to human-gate reconciliation, not silently closed; referenced in KNOWN-LIMITS)
- [x] **Soak/scale validation** (opt-in `EDDY_SOAK=1` harness, like golden: ~3h transcript compile bounded <20s [no quadratic blowup], 500-candidate shorts cap, 1000-source batch queue w/ failure isolation, byte-identical recompile at scale — each with a wall-clock budget) (`tests/test_soak.py`, +4 tests)

### v0.7 items (operability & safety — all autonomous-able)
- [x] **Sidecar SRT + WebVTT** of the final cut in the launch kit (accessibility + SEO) (`render/subtitles.py`/`launch_kit.py`, +5 tests)
- [x] **Token + cost accounting + spend cap + per-run summary** (anthropic/openai log usage→cost; loop aborts at `max_run_cost_usd`; run prints editorial $) (`cost.py`/providers/`controller.py`, +5 tests)
- [x] **`eddy bundle` redacted diagnostic archive** (audit trail + env zip; transcript text redacted + home paths scrubbed; no footage/transcript/faces) (`bundle.py`/`cli.py`, +3 tests)
- [x] **Structured audit log** — substantially covered: `receipts.jsonl` is the structured per-run log (every model call/gate/cost/error), already bundled by `eddy bundle`. (`--quiet`/`--verbose` console-level control deferred as low-value polish.)
- [x] **Creator-facing review notes** (`final/REVIEW.md`: plain-language "N moments Eddy was unsure about" + timestamps + over-ceiling banner + QA verdict, indexed in the kit) (`package/review.py`/`launch_kit.py`, +5 tests)
- [x] **Face-upload consent gate + AI-generated disclosure** (thumbnails opt-in via `thumbnails.consent_to_upload`; `final/AI-DISCLOSURE.md`) — NSFW/deception MODEL moderation deferred (needs a moderation API) (`config.py`/`thumbnails.py`/`launch_kit.py`, +2 tests)
- [x] **Prompt-injection hardening** (transcript data-fenced in the cut-planner + judge; injection patterns flagged to receipts; deterministic gates remain the backstop) (`safety.py`/`cutplan.py`/`judge.py`, +4 tests)
- [x] **GDPR/CCPA purge** (`eddy purge` removes transcript/face-frames/caption-text PII, keeps deliverables; `--full` erases the run; `--dry-run`) (`clean.py`/`cli.py`, +3 tests)
- [x] **Opt-in anonymized failure beacon** (OFF by default; sends only version/OS/python/ffmpeg/stage/error-class — never message/paths/footage) (`beacon.py`/`config.py`/`cli.py`, +4 tests)
- [x] **Generalized the personal Chrome-pairing guard** — exit-43 hardcoding replaced by configurable `transient_exit_codes` (empty default; no author-specific behavior shipped) (`cli_subprocess.py`/`config.py`, tests updated +1)

### v0.5 items
- [x] **Fix QA detect filters** (silencedetect → `-af`, returncode check, fail-loud not false-pass) (`deterministic.py`, +6 tests)
- [x] **Crash-proof duration resolution** (format → longest stream → typed unknown; fail-loud where needed) (`probe.py`, +6 tests)
- [x] **Whisper language auto-detect + `--language` + health warnings** + dropped personal vocab prompt. Forced-language mismatch warning does a REAL independent detect_language pass (was dead vs info.language — review M1 fixed). (`whisper.py`/`config.py`/`cli.py`/`controller.py`, +7 tests)
- [x] **Ingest gates** (accept webm/avi/ts/mts/3gp/wmv/flv; decodability preflight fails loud on corrupt/0-byte/no-video) (`runs.py`/`controller.py`, +7 tests)
- [x] **Empty/no-speech is a first-class outcome** (fail fast, don't cache an empty transcript) (`whisper.py`, +2 tests)
- [x] **Live progress + ETA** (per-iteration cut N/M · quality · judge · over-ceiling · elapsed + ETA; transcribe banner; total elapsed) (`controller.py`, +3 tests)
- [x] **Top-level error handler + crash log** (friendly "what happened + next step" + persisted traceback, nonzero exit) (`errors.py`/`cli.py`, +6 tests)
- [x] **`tests/conftest.py` + synthetic lavfi fixtures + markers** (needs_ffmpeg/e2e/slow; real-probe coverage) (`conftest.py`/`test_fixtures.py`, +5 tests)
- [x] **Fixture-backed render→QA e2e** (real ffmpeg render + deterministic gates on synthetic media, source unmutated) (`test_e2e_render.py`, +1). Full-run-with-stubbed-model e2e deferred to v0.5.x.
- [x] **Unit tests across untested modules** (doctor/retakes/protect/pack/captions/copy/layout/simulate, +88 tests via an 8-agent self-verified Workflow fan-out)
- [x] **Loop-resume integrity tests** (plateau/best persistence, recovered flag, model-pin/drift) (`test_loop_resume.py`, +7)
- [x] **Provider contract tests** (ollama/anthropic/openai: text+schema, retry-once→ProviderError, NaN reject, key/timeout) (+28 via Workflow) — surfaced a real openai key/base_url passthrough gap (fixed next)
- [x] **`compile_edl` Hypothesis fuzz** (finite/in-bounds/sorted/non-overlapping/positive invariants under random cuts + protections) (`test_compile_fuzz.py`, +2 property tests)
- [x] **Golden editorial suite** (opt-in EDDY_GOLDEN, pinned local qwen, tolerance assertions) — VERIFIED green against the real qwen36-27b-codex:q4 in 16.8s (`test_golden.py`, +1)

### v0.6 items (autonomous-able marked ⚙; human-gate marked 🔒)
- [x] ⚙ **Runtime encoder resolver** (probe `ffmpeg -encoders`; videotoolbox/nvenc/qsv → libx264 fallback) — replaced hardcoded h264_videotoolbox at all 4 sites (`media/ffmpeg.py`+render, +7 tests)
- [x] ⚙ **Cross-platform caption fonts** (macOS/Linux/Windows candidates + glob fallback + non-silent warning; Pillow default is real/scalable) (`captions.py`, +4 tests)
- [x] ⚙ **Cross-platform hardware detection** (macOS sysctl / Linux /proc / Windows GlobalMemoryStatusEx + psutil fallback; unmeasured = None not 0) (`doctor.py`, +6 tests)
- [x] ⚙ **doctor preflight (ffmpeg>=8/ffprobe/encoder/free-disk) + `eddy run --dry-run`** (checks env + footage decodes, exits before the expensive pipeline) (`doctor.py`/`cli.py`, +4 tests)
- [x] ⚙ **`eddy clean` (+ `--dry-run`) + disk-usage in `eddy status`** — prunes segment scratch/proxies/16k WAV, keeps deliverables + audit trail (`clean.py`/`cli.py`, +2 tests)
- [x] ⚙ **Pinned deps (upper bounds) + committed `requirements.lock`** (47 runtime deps; mac-resolved — cross-platform uv.lock is a follow-up) (`pyproject.toml`)
- [x] ⚙ **Config schema migration (version-stamp + migrate-forward) + tolerant loader + runs_dir case fix** (`~/.eddy/runs`; malformed config no longer bricks every command) (`config.py`/README, +5 tests)
- [x] ⚙ **Tiered local recommendation + guided pull** (16-32GB → smaller local model not cloud; `ollama pull` guidance; light-machine note) (`doctor.py`, tests updated)
- [x] ⚙ **3-OS CI matrix YAML + wheel smoke** authored (`ci-matrix.yml`: mac/ubuntu/windows real render + built-wheel `python -m eddy` smoke) + `__main__.py` — runs live once the remote exists (🔒 #3)
- [ ] 🔒 Private GitHub remote (human-gate #3) — needed for the CI matrix to run live
- [ ] 🔒 Code-signing certs (human-gate #2) — Apple Developer ID + Windows Authenticode
- [ ] 🔒 Real install channel / publish (human-gate #4) — signed installer or PyPI

## Human-gate batch (accumulating)
1. Legal sign-off — commercial EULA + AUP + third-party NOTICE; ffmpeg LGPL build + qwen/Whisper commercial-use rights.
2. Code-signing certs — Apple Developer ID + Windows Authenticode.
3. Private GitHub remote — for the 3-OS CI matrix + wheel smoke test.
4. Publish authorization — channel choice + public release.
5. Real-footage dogfood + capped real-API spend.
6. Any new external account/spend.

## Log
- v0.4 model-boundary fix committed `1283f5a`; suite 100 → 113 green.
- v0.4 atomic+tolerant run-state IO; suite 113 → 119 green.
- v0.4 judge hardening (clamp 1–10, .get defects, in-try processing); suite 119 → 126 green.
- v0.4 validate_against recursive (nested required/types/enums); suite 126 → 134 green.
- v0.4 apostrophe concat (shared concat_quote) + path gate (is_relative_to, all outputs); suite 134 → 142 green.
- v0.4 slug wrong-footage guard (re-hash on reopen) + --resume wired; suite 142 → 147 green.
- v0.4 git-derived version (was stale 0.1.0) + eddy --version + receipt stamp; suite 147 → 150 green.
- v0.4 CI: .github/workflows/ci.yml (ruff+mypy+pytest); cleaned 33 ruff issues (incl. moving controller.py imports) + 9 mypy errors to zero; suite stays 150 green. Historical note superseded by the public GitHub repo decision on 2026-06-23.
- v0.4 cumulative (resume-surviving) model-call + per-process wall-clock budget (was dead config); suite 150 → 154 green.
- v0.4 model pin (provider+model recorded per run, drift warning); suite 154 → 158 green.
- v0.4 privacy honesty: --local-only/EDDY_OFFLINE forces local brain + whisper local_files_only + thumbnail skip + egress disclosure + PRIVACY.md/README fix; suite 158 → 162 green.
- v0.4 MERGED to master, tagged v0.4 (review SHIP-WITH-NITS, nits cleared). v0.5 branch cut.
- v0.5 QA detect fix (175→), duration resolution, whisper language, ingest gates, no-speech gate, conftest+fixtures: suite to 194.
- v0.5 unit-test sweep (8-agent Workflow, self-verified): doctor/retakes/protect/pack/captions/copy/layout/simulate; +88 tests; suite 194 → 282 green, ruff+mypy clean.

## Post-GA (trunk-based on `main`, public GitHub remote)
- **v1.1–v1.2** — mascot/MCP/plugin + the full-screen Textual TUI (tagged v1.1.0, v1.2.0).
- **v1.3 "Eddy, simpler"** — TUI minimalism + honest feedback + reach (tagged v1.3.0; see docs/decision-log.md).
- **v1.4 "No Sharp Edges"** (tagged v1.4.0) — 13-item batch from a 7-subsystem assessment, all autonomous:
  five verified crash/leak fixes (console UTF-8, shorts video-None guard, subprocess error redaction,
  copy fallbacks, whisper plain errors); in-app failure (F3) + artifact-preview (F4) modals + honest
  reveal + offline thumbnail placeholder; package_run e2e + JobManager/CliProvider unit tests; retake
  pause signal + post-cut pacing feedback; matrix-on-main + Node-20 action bumps + cross-platform
  wheelhouse (`--target`). Suite 581→618, coverage 74.0%, ruff+mypy clean, fast CI + matrix green.
- **v1.5 "Focus edit"** (unreleased; lands in the next tag) — drag-drop paths + a natural focus brief
  ("edit this video: <path> - only focus on X"). Soft steer by default; an opt-in **extract** mode
  (auto-armed by "only keep / only focus on" phrasing) relaxes the keep-most protection gates so it can
  drop the off-topic majority. Brief persists in the run manifest (resume-safe), audited in x_eddy only
  (no schema/enum break). CLI `--focus`/`--extract`; TUI asks what to produce each time. 5 trunk
  commits; suite 618→644, coverage 74.5%, ruff+mypy clean; verified via free dry-run on the real 62-min
  source. Known limit: judge isn't yet brief-aware (aggressive extracts may ship best-effort).
- **v1.6 "Extract continuity"** (unreleased) — closes the v1.5 known limit after the first live extract
  (62-min Codex call → 21 fragments, judge 2.18, 0/3 ship) proved targeting but exposed quality. Four
  fixes: (1) **brief-aware judge + ship panel** — `_focus_judge_context` stops penalizing an extract for
  the standalone-video conventions it can't meet (hook/completeness/CTA) while keeping continuity/pacing
  strict, so a clean extract can actually clear the gate; (2) **deterministic bridge-merge** — a new
  `compile_edl(extract=True)` pass fuses keeps separated by ≤6s gaps into a few contiguous blocks, snaps
  edges to phrase boundaries, drops <2.5s slivers (normal edits byte-identical); (3) **extract-aware
  revision directive** — continuity-only (restore/extend/tighten), never `drop_beat`, killing the v1.5
  iter-2 thrash; (4) **long-source JSON robustness** — `extract_json` salvages a truncated cut list
  (no silent corruption) + adaptive `num_ctx`. Full suite green, ruff+mypy clean; new
  `test_continuity_pass.py` + extended focus/boundary tests. Live 62-min re-run pending.
- **v1.7 "Best-of-N extract brain"** (unreleased) — from the /goal pursuit of a stronger, lower-variance
  editorial brain. A 5-draw $0-local baseline quantified the wall: the same prompt gave judge 4.27–7.82
  (stdev 1.154), blocks 5–82, dur 2.3–17.2 min, and **~45% of single draws are over-ceiling catastrophes**
  (the local 27B simply fails to extract). Fix: **best-of-N self-consistency** for the iteration-1 extract
  draft (`src/eddy/edit/ensemble.py`) — sample N drafts, pick the winner by a deterministic render-free
  selector (feasibility band → fewest blocks → objective). Opt-in via `loop.ensemble_n` (default 1 = off,
  extract-gated, normal/steer edits byte-identical). **Confirmed at N=5 on a full 5-draw run vs baseline:
  judge stdev 1.154→0.339 (↓71%), quality stdev 0.658→0.270 (↓59%), over-ceiling catastrophes 1→0,
  durations tighter (mean 6.75→3.78 min).** Block-count stdev only ↓9% — residual from bad groups (a draw
  whose N drafts are all bad) and the revise loop re-bloating a tight pick (confirm2-d5: ensemble picked
  8 blocks, loop grew it to 75); both are deeper than the ensemble (brain draft-quality + best()-by-quality)
  and are documented future work. clean-ship stays 0/5: blocked by the deterministic `no_dead_air`/
  `silent_motion` gates (an audio-energy-vs-Whisper-word disagreement — quiet/trailing speech flagged silent
  but un-cuttable; NOT the brain) + a judge ceiling ~7.8<8.0. Strict ship-gate success was relaxed to the
  determinism win WITH Lennox's explicit approval. Recommended setting for extracts: `ensemble_n = 5`
  (costs ~5× the iter-1 cutplan time). Suite 676 green, cov 75.1%, ruff+mypy clean; 8 ensemble tests.
- **v1.7.3 "Honor the brief's runtime" + stale-install root cause** (2026-06-22) — Lennox's live run of
  "make it focus on my 5-10 minute explanation of what Codex is" did not produce a focused 5-10 min cut.
  **Root cause #1 (dominant):** the `eddy` on PATH is a **pipx install frozen at v1.4.0** (built from
  `~/eddy[mcp]` before focus existed) — `eddy run --help` has no `--focus`/`--extract`; all of
  v1.5→v1.7 lives only in the working tree, never reinstalled. **Fix: reinstall pipx `eddy` editable
  from the repo** so the binary tracks HEAD and never drifts again. **Root cause #2 (real gap on HEAD):**
  the "5-10 minute" was never parsed — target defaulted to 12 min, ceiling 14 min. **Fix:**
  `duration_from_brief()` (`tui/intents.py`) parses a runtime from the brief → loop target + length
  ceiling, wired in `cli.run()` only when no explicit `--target-minutes` and the default format (named
  formats keep their deliberate ceiling). +16 tests; suite **692 green**, cov 75.34%, ruff+mypy clean.
  No full $0 render this turn (the fix is target+ceiling correctness, not a re-render). Known follow-up:
  best-of-N selector still ranks over-ceiling against the **config** ceiling, not the per-run brief one.
- **v1.7.4 "Simpler chooser + honest progress" (TUI)** (2026-06-22) — from two live-run screenshots.
  **(1) Chooser:** the "What should Eddy make?" modal clipped its 4th button (Cancel) — 4 buttons in a
  fixed 64-col dialog overflowed. Dropped the Cancel button (3 buttons never clip); `esc` + a **click on
  the backdrop** (`OutputScreen.on_click`) both cancel; the triple-redundant key hints collapse to one
  "what each makes" line. **(2) Progress:** "step 1 of 10" was fixed and wrong for runs that skip stages.
  The engine now records the **actual per-run stage plan** (`_run_plan` + `RunState.set_plan` → state.json)
  and the monitor renders a **stage breadcrumb** (`✓ done · ▸ current · dim pending`) + honest "step k of
  N" (`phases.breadcrumb` / plan-aware `phases.progress`); edit loop stays one "Editing" step with a live
  "(pass N)"; banner subtitle `editing` → `starting`. `phases.py` stays Textual-free; engine imports no
  TUI. +13 tests (`test_tui_output.py`, `test_tui_phases.py`, `test_run_plan.py`); suite **704 green**,
  cov 75.29%, ruff+mypy clean. A default video-only run shows 6 honest stages, not 10. No full TUI run
  rendered to completion this turn.
- Human-gate batch (signing certs, publish channel, legal sign-off, real-footage dogfood + capped API
  spend) remains open by design — none are coding-agent tasks.
