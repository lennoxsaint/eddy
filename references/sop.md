# The editing SOP (source of truth)

The canonical 6-step edit, in order, with V3's corrections applied. This is the contract Lennox
gave; obey it exactly, but let taste fill the gaps between steps.

## The 6 steps (do in order)

1. **Camera/webcam track → rounded corners on all four corners.** Done in the composite
   (`scripts/composite_render.py`), NOT Descript — the Descript web app has no corner control.
   Uses the frozen radius from `layout-constants.md`.
2. **Screen recording track → rounded corners on all four corners.** Same — composite layer.
3. **Studio Sound at 100% intensity on the script/audio track.** Real Descript, audio-only
   (`scripts/descript_studio_sound.py`). Default 100%; `--studio-sound N` to dial down if it ever
   sounds processed (Lennox's older config used 80).
4. **Shorten word gaps.** Only gaps **>0.2s** get tightened to **0.1s**. Sacred/vulnerability
   pauses are exempt (`retention-policy.md`). Exact, deterministic — done in `scripts/splice.py`,
   not Descript's single-threshold knob.
5. **Remove ALL retakes**, keeping the **last take** of each repeated phrase (last-take bias unless
   the last take is demonstrably worse). **No regenerate/overdub** — deterministic removal only.
6. **Edit the script for clarity at MEDIUM level** — remove redundant explanations, tangents, and
   filler while keeping the core message and natural flow. **No regenerate/overdub.** (Today's
   request overrides the older "heavy" SOP.)

## SOP steps that are NOT for the YouTube long

The older local SOP checklist also lists these — they belong to Shorts / Threadify-format, not the
16:9 long. Do NOT apply them to the long:

- "Change video to square aspect ratio" → Shorts only.
- "Add Threadify background" → Shorts / Threadify-format only.
- "Change to 1.1× speed" → OFF by default. Only if `--global-speed X` is passed, and even then it
  must skip sacred/vulnerability spans (global speed-up conflicts with preserving breath).

## Order of operations note

Retakes (step 5) and clarity (step 6) are **transcript-level decisions you make**, expressed as a
cut list. Gaps (step 4) and corners/Studio-Sound (steps 1-3) are **mechanical** and executed by the
frozen scripts. You decide *what*; the scripts execute *how*.
