# Hook doctrine — the 90%

The hook is ~90% of the video's value. The discovery hover preview makes the first visible frame,
the first 3 seconds, and the first 30 seconds separate acceptance surfaces. Budget effort there
accordingly while keeping the body produced and semantically paced.

## Step 1 — Establish the promise BEFORE editing the hook

The hook is optimized to the strongest honest viewer promise the footage can carry. Eddy v3.0 does
not emit packaging assets, but it still needs an internal promise target before cutting:

1. If the folder has a decision card or intelligence brief, read it as source context.
2. Otherwise infer the strongest specific outcome, counterintuitive claim, or high-stakes proof
   from the transcript. Write it to `viewer-promise.md`; do not generate titles or thumbnails.

The viewer promise is the north star. The hook must **pay off exactly that promise**.

## Step 2 — Structure of a working opening

- **0-30s cold open (hook):** land the promise immediately. No "hey guys, what's up", no slow
  throat-clearing, no logo. Open on the sharpest, most curiosity-provoking beat that the viewer
  promises. Keep the chosen hook line **word-for-word** — do not paraphrase it.
- **30-60s preview bridge:** tease 2-3 upcoming reveals ("in the next few minutes you'll see X, Y,
  Z"). This creates micro-curiosity-gaps that pull viewers across the hook→content cliff (a large
  retention drop happens right here).

## Step 3 — Score the hook (rubric)

Score the drafted 0-60s. Re-cut until it clears threshold (redo up to 3, per verification):

| Dimension | Question | Pass bar |
|---|---|---|
| Promise match | Does it deliver the exact viewer promise? | must pass |
| Cold-open strength | Would a stranger stop scrolling in the first 3 seconds? | must pass |
| Curiosity gap | Is there an open loop the viewer needs closed? | must pass |
| No dead air | Zero slow intro, filler, or setup before the promise lands? | must pass |
| Payoff visible | Does the bridge promise concrete upcoming reveals? | must pass |
| **Proof on screen** | Is every concrete artifact the hook NAMES (a post, receipt, demo, screenshot, number) actually **shown on screen within 0-60s** — not just spoken? A hook that says "look what this post did" and never shows the post fails. Use the real screenshot if present in `source/`; else render it on-brand (HyperFrames `receipt_print`). | **must pass** |
| Visuals | Is the first-60 motion (see `motion-layer.md`) carrying the promise? | should pass |

## Step 4 — Three full versions, one per hook (A/B/C)

Output **three complete longs that share one body edit** and differ only in a **self-contained hook
opening**. This replaces the old "1 main + cold-open clips" — each hook is its own whole video so
Test & Compare measures a real like-for-like swap.

- Pick the 3 strongest distinct angles the footage supports (e.g. `theft`, `free-any-model`,
  `mechanism`). Each hook must independently clear the Step 3 rubric — including **Proof on screen**.
- The body edit is rendered **once** and reused; only the 0-60s opening changes. Name them by angle:
  `final/long-<angle>.mp4` (e.g. `long-theft.mp4`, `long-freemodel.mp4`, `long-mechanism.mp4`).
- A hook is **self-contained**: it carries its own proof and needs no context from the other two. Do
  not defer the proof to "later in the video" — show it inside the hook.
- Never overdub to fix a misspoken hook line. If the recorded words are factually off (wrong
  name/pronoun), pick a cleaner take or don't lead on that phrase, and log it in `spot-check.md`.

## Step 5 — Hook visuals

The hook is where the "$100k motion graphics" go. Brief HyperFrames to animate the promise for the
first 30-60s (see `motion-layer.md`). The visual and the spoken hook must reinforce the same
promise — not compete.

For v3.2, author three distinct semantic scene timelines and rank the treatments after muted/mobile
inspection. Auto-select only when the leader is certain and more than five points clear. Otherwise
use `eddy opening-candidates` and make a receipted `eddy select-opening` choice. Selection does not
erase the alternates; it determines `long-primary.mp4`, while all three complete Longs still ship
for like-for-like comparison.
