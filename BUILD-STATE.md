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
| v0.6 crossplatform | `v0.6-crossplatform` | **next** |
| v0.7 operability | `v0.7-operability` | pending |
| v0.8 breadth | `v0.8-breadth` | pending |
| v1.0 GA | `v1.0-ga` | pending |

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
- [ ] ⚙ Pinned deps + committed lockfile; reconcile requires-python
- [ ] ⚙ Config/EDL schema migration (version-stamp + migrate-forward) + XDG runs_dir (~/Eddy vs ~/eddy)
- [ ] ⚙ Guided Ollama onboarding + tiered local recommendation (not the 32GB cliff)
- [ ] ⚙ 3-OS CI matrix YAML + wheel smoke test (authored; runs once remote exists)
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
- v0.4 CI: .github/workflows/ci.yml (ruff+mypy+pytest); cleaned 33 ruff issues (incl. moving controller.py imports) + 9 mypy errors to zero; suite stays 150 green. (CI runs live once the private remote exists — human-gate.)
- v0.4 cumulative (resume-surviving) model-call + per-process wall-clock budget (was dead config); suite 150 → 154 green.
- v0.4 model pin (provider+model recorded per run, drift warning); suite 154 → 158 green.
- v0.4 privacy honesty: --local-only/EDDY_OFFLINE forces local brain + whisper local_files_only + thumbnail skip + egress disclosure + PRIVACY.md/README fix; suite 158 → 162 green.
- v0.4 MERGED to master, tagged v0.4 (review SHIP-WITH-NITS, nits cleared). v0.5 branch cut.
- v0.5 QA detect fix (175→), duration resolution, whisper language, ingest gates, no-speech gate, conftest+fixtures: suite to 194.
- v0.5 unit-test sweep (8-agent Workflow, self-verified): doctor/retakes/protect/pack/captions/copy/layout/simulate; +88 tests; suite 194 → 282 green, ruff+mypy clean.
