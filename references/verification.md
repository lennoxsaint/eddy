# Verification + self-heal (≤3)

Work is not done until emitted behaviour is checked. Two layers: deterministic gates (machine) and
model rubrics (you). On any failure, redo the offending stage up to **3 times**, then ship the best
attempt and record what's unresolved in `spot-check.md`. Bounded on purpose — V1's unbounded loop
plateaued and stalled.

## Deterministic gates (`scripts/verify.py`)

- **Audio parity** — Studio Sound output duration within ±1% or 1s of the audio it was given
  (Descript must not have changed timing). Fail → re-run or fall back per the script.
- **Gap band** — post-edit median/P95/max gaps within `layout-constants.md` band; no gap over hard
  max (0.28s) outside sacred spans.
- **Beat completeness** — every `keep` beat id from `edit-plan.md` is present in the final cut.
  Losing one is a hard fail.
- **Protected count** — `protected_count` (sacred spans) preserved end-to-end.
- **Layout asserts** — PiP present at the right position/radius; corners applied; Shorts stack
  geometry correct.
- **Caption sync** — cue timings align to word timings; no cue overlaps the next by >1 frame.
- **Loudness** — final mix hits the loudness target; no clipping.

## Model rubrics (you judge; trigger a redo)

- **Hook self-check** — score 0-60s against the `hook-doctrine.md` rubric. Below threshold →
  re-cut the hook.
- **Retake sweep** — scan the final transcript: any repeated-phrase pair still present? Did you
  keep the last take?
- **Cohesion pass** — "watch" the edited transcript+timings start to finish. Jumpcuts, dangling
  references ("as I said earlier" when that beat was cut), lost context? Fix.
- **Gutting check** — did any sacred or grounded beat get cut or compressed? Restore it.

## Receipts (trust without review)

- `edit-plan.md` — the beat map + section structure (also the human-readable EDL).
- Every cut logged with a one-line reason.
- `spot-check.md` — cuts you were unsure about (timestamp + reason) for optional after-the-fact
  review. This is the artifact that lets Lennox ship without watching the whole thing.
- Final Second Brain run log through the canonical gateway.

## Definition of shippable

All deterministic gates green, all model rubrics addressed (or the residual honestly flagged), and
`spot-check.md` written. Then — and only then — do the full-res render and hand off.
