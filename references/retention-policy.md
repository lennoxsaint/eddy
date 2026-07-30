# Retention policy — edit for retention without gutting

Raw length is meaningless. A 70-min recording riddled with gaps might be 10 min of real content; a
180-min session might be 15. So the guardrail is **not** a runtime ratio — it is **beat
completeness**.

## The beat map (do this first, in `edit-plan.md`)

Map every **distinct substantive beat**: a point, an example, a story, a proof, a demo. For each,
record: `id`, timestamp span, one-line summary, and a class:

- `keep` — a unique substantive beat. **Guaranteed to survive.**
- `duplicate` — the same point made twice (a re-explanation, a repeated example). Keep the best one.
- `tangent` — a genuine digression that doesn't serve the narrative arc. Candidate to cut.
- `retake-group` — multiple attempts at the same line. Keep the **last take** (last-take bias),
  unless it's demonstrably worse (flubbed, cut off, worse energy).

## The anti-gutting guarantee

- **Every `keep` beat survives.** Losing one is a hard failure, not an edit.
- You may only remove **dead weight**: word gaps, retakes, filler ("um", "so basically", restarts),
  redundant re-explanations (`duplicate`), and true `tangent`s.
- Runtime is whatever's left after dead weight is gone. Do not chase a length.

## Optional target dial

If `--target-min N` is given, treat it as a **trim-aggressiveness dial**, not a hard cut:
- Lean harder on trimming `tangent`s and `duplicate`s to approach N.
- You still **cannot drop a `keep` beat** to hit N. If N is unreachable without gutting, ship the
  shortest honest cut and note the residual in `spot-check.md`.

## Sacred zones (hard — never cut, speed, or compress)

- **Vulnerability / emotional moments** — genuine struggle, real emotion, hard-won realizations.
  These are the #1 subscriber-conversion driver. Never speed up, never gap-compress, preserve the
  breath and the pauses. (Lennox's most-repeated rule.)
- **Hook 0-30s** — word-for-word, untouched.
- **Preview-promise bridge 30-60s** — the defense against the hook→content retention cliff.

Mark sacred spans in `edit-plan.md`. The composite carries a `protected_count`; `verify.py` asserts
it survived the edit end-to-end.

For Strategy Profile V7, the Opening Edit Blueprint is also a retention contract. Every planned
scene through second 60 maps to the delivered timeline. You may replace a treatment when real
footage or mobile legibility requires it, but you may not silently remove, reorder, or change the
scene's communication job. Record the replacement and its proof as an opening deviation receipt.

## Bias-to-keep + spot-check (autonomy without stalling)

Run fully autonomous — never stop mid-edit to ask. But:
- **Default to KEEPING** grounded / off-script examples. Lennox values authenticity over duration;
  the real examples ARE the content that differentiates him. When unsure, keep it.
- Every cut you were unsure about — anything you classified `tangent` or `duplicate` and removed —
  goes in `spot-check.md` with its timestamp and your one-line reason. This is what lets him trust
  the one-shot output without a blocking review.
