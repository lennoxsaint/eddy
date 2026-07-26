# Verification + self-heal (minimum three full passes)

Work is not done until emitted behaviour is checked. Complete at least three full
watch/critique/repair passes. On any failure, quarantine the red candidate and change strategy.
Continue until all evidenced checks score 100/100 or an exact `external_blocker:` or
`technical_blocker:` remains. A retry count alone is never a terminal blocker.

## Deterministic gates (`scripts/verify.py`)

Run the gate suite on **every emitted file — each long AND each Short**, not just the primary long.

- **Audio parity** — Studio Sound output duration within ±1% or 1s of the audio it was given
  (Descript must not have changed timing). Fail → re-run or block; no raw/local fallback is final.
- **A/V duration sync** (`av_sync_duration`) — delivered audio and video stream durations differ by
  no more than 80ms. Eddy preserves source-relative segment timestamps so frame rounding cannot
  accumulate one extra video frame at every cut.
- **Gap band** — post-edit median/P95/max gaps within `layout-constants.md` band; no gap over hard
  max (0.28s) outside sacred spans.
- **Max internal silence** (`max_internal_silence_ok`) — `silencedetect` on the **rendered** file:
  no unprotected silence longer than `--max-deadair` (0.28s). Protected content may retain meaning,
  but `protected_pause_ceiling` blocks any protected silence above 0.8s. This catches the dead-air
  that word-only tightening missed (the 16s / 4s survivors). Runs on the source-of-truth audio, not
  the segment receipt.
- **Speech ratio** (`speech_ratio_ok`) — 1 − (total silence / duration) ≥ floor; a low ratio means
  dead air slipped through.
- **Retake scan** (`retake_repeat_scan`) — **re-transcribe the final render** (`transcribe.py` on the
  output) and pass its words as `--final-words`; flags adjacent duplicate 4-gram phrases (a leftover
  retake said twice). If it fires, review each flag — real retake → re-cut; genuine repetition →
  override. This is the machine half of the retake sweep; do it for **Shorts too**.
- **Delivered editorial truth** (`delivered_editorial_truth`) — run the same repeat, reset-loop, and
  false-start detector over every delivered-media transcript. Any unresolved survivor blocks.
- **Evidence-bearing Short** — source-mapped screen proof covers at least 25% of a dual-source Short
  and three overlay-free delivered-frame samples match transformed raw screen frames. Its hook and
  supporting proof beats each show at least three perceptual states at 10 fps and stay frozen for
  less than 80% of their duration.
- **Beat completeness** — every `keep` beat id from `edit-plan.md` is present in the final cut.
  Losing one is a hard fail.
- **Protected count** — `protected_count` (sacred spans) preserved end-to-end.
- **Layout asserts** — PiP flush to the bottom-right corner at the right size/radius; screen fills
  the frame (no black bars) with slight rounded corners; Shorts stack geometry correct.
- **V3.2+ choreography contract** — frame hash matches; every source ref exists under the source
  snapshot or run; opening/body/Short cadence, evidence authority, layout diversity, and transition
  limits validate before render. HyperFrames lint, validate, and inspect receipts must be green.
- **V3.3 body-structure contract** — the source contract ref/hash is present; route clarity is at or
  before second 30; 3-5 section IDs match Sage order; every shared-body scene maps exactly once;
  every section has a real proof scene; and every non-final boundary has a reset scene, transition
  card, and spoken callback.
- **Opening selection** — ranking and selected opening are receipted. A top-two gap of five points
  or less, or uncertain leading judgment, must pause before finalization.
- **Caption sync** — cue timings align to word timings; no cue overlaps the next by >1 frame.
- **Caption terminal punctuation** — the generated ASS token proof preserves source `.`, `?`, and
  `!` sentence endings while continuing to suppress stray decorative punctuation.
- **Loudness** — final mix hits the loudness target; no clipping.
- **Contract binding** — host packet, v3.4 plan, receipts, and final evidence expose matching
  profile, design, landscape frame, portrait frame, HyperFrames doctrine, correction-eval, and
  rubric hashes.
- **100-point evidence** — exactly 100 one-point checks pass. Every point has a file, frame,
  timestamp, hash, playback, or measurement reference. Audience performance remains `NOT_RUN`;
  final authority remains `owner_taste_lock`.

## Model rubrics (you judge; trigger a redo)

- **Hook self-check** — score 0-60s against the `hook-doctrine.md` rubric. Below threshold →
  re-cut the hook.
- **Retake sweep (long + every Short)** — the `retake_repeat_scan` gate flags duplicates; you make
  the call. Because Shorts are clipped from the edited body, a retake boundary can land inside a
  Short even when the long is clean — so **re-transcribe each Short** and sweep it independently. If
  a retake survived, surgically remove it from that Short's source span, re-splice, re-caption. Keep
  the last take.
- **Cohesion pass** — "watch" the edited transcript+timings start to finish. Jumpcuts, dangling
  references ("as I said earlier" when that beat was cut), lost context? Fix.
- **Gutting check** — did any sacred or grounded beat get cut or compressed? Restore it.

## Receipts

- `edit-plan.md` — the beat map + section structure (also the human-readable EDL).
- Every cut logged with a one-line reason.
- `spot-check.md` — cuts you were unsure about (timestamp + reason) for review. The no-review claim
  remains locked until five diverse owner-approved dogfoods are green.
- `visual-choreography/` — project frame, opening ranking/selection, per-surface manifests,
  animation maps, provenance, shared-body hash, and 0/1/3/10/30 comparison surfaces.
- Final Second Brain run log through the canonical gateway.

## Setup failures & fallbacks (degrade gracefully, don't abort)

Autonomy means never stalling on a non-essential layer. On a stage failure:

- **`DESCRIPT_API_KEY` missing / Studio Sound fails** — HARD stop for every final long. API success
  and duration parity do not count unless the calibrated Effect-Survival Gate also passes. Report
  clearly and halt; do not ship the raw or the dev-only
  `EDDY_FAKE_DESCRIPT` audio as final.
- **No screen-recording track** — switch to the talking-head layout (`composite_render.py th` /
  `short --face`). Not an error.
- **WhisperX transcription fails** — retry once; if it still fails, stop (everything downstream
  needs word timings). Surface the exact stderr.
- **HyperFrames / motion engine missing or errors** — HARD stop for final promotion. Preserve the
  clean cut as a candidate, quarantine the failed attempt, and report the exact motion blocker.
- **`embedded-captions` unavailable** — fall back to the V1 caption style in `captions.py` (same
  constants); never ship without karaoke.
- **Render fails at full-res** — re-run once at proxy to isolate; fix the offending stage, then
  full-res again (counts against the ≤3 self-heal budget).

## Definition of shippable

All deterministic gates green, all model rubrics addressed, and `spot-check.md` written. Then — and
only then — promote the full-resolution artifacts into `final/`. Residual mandatory failures produce
a Blocked Attempt instead.
