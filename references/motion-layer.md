# Interactive motion layer (the Tariq layer)

Principle (from Tariq @trq212 editing a talk with Fable 5): having visuals as **HTML** lets the
model turn static content into **dynamic animations** — animated section intros, slides that come
alive, varied slide+speaker layouts. We adopt this **scoped to high-leverage moments**, not the
whole video, so it stays interactive without becoming bloated.

## Where motion goes (scope)

1. **Hook / first 60s** — the "$100k motion graphics." Animate the packaging promise. Highest
   priority; this is the 90%.
2. **Section-intro / chapter cards** — a short animated card at each major section boundary (like
   Tariq's "Dealing with the Grief" card and the "the map is opening up" animation). Pull section
   titles + timestamps from `edit-plan.md`.
3. **A handful of concept slides** — YOU pick 3-8 key concepts (a framework, an equation, a quote, a
   list, a data point) and render them as animated HTML composited with the webcam. Do not animate
   every second — only the concepts that genuinely benefit.

Everything else stays clean webcam + screen recording. If there's no clear win, don't add motion.

## Engine — HyperFrames is the default (overrides the old minimal-type mandate)

**The previous "minimal premium typography in ffmpeg" mandate is retired.** Motion is now
**HyperFrames by default**, and it is **iconography- and image-forward, not text**. The graphics
should be a **visual representation of the words being spoken** — icons, screenshots, diagrams,
receipts, product chrome — with text as a supporting label at most, never the lead.

- **Default engine — HyperFrames (`scripts/motion_render.py`).** HTML → video via the
  `~/eddy-v2` runner, in the **`threadify-fc` identity, restrained profile** (palette + Avenir/Space
  Mono type + brand atoms; allow `receipt_print`, `ledger`, `card_handoff`, section-intro cards,
  icon/image concept slides; **disallow** the FWED mascot, the fire register, `type_slam`, and the
  `cursor_press` CTA — this is a tutorial, not a launch video). Every off-screen reference the
  narration makes ("the post showed…", "the email said…") gets an on-brand icon/image, not a caption.
  - **Machine safety (hard rule):** headless Chromium, GPU off; **never run a HyperFrames capture
    concurrently with an ffmpeg encode**; proxy (`draft`) in the self-heal loop, `hd` once at the end.
- **Fallback only — `scripts/motion_type.py`.** The old ffmpeg type engine. Use ONLY when HyperFrames
  is unavailable/erroring or for a trivial one-word label where a full HTML render is overkill. It is
  no longer the default and no longer the aesthetic target.
- **Karaoke: `embedded-captions` `anchor` identity** (long) / `scripts/karaoke_ass.py` (Shorts split
  stack) — the clean, calm, verbatim look. Never a per-word storm (Tariq's critique).
- **Base composite: V1 ffmpeg** (`scripts/composite_render.py`) — full-frame screen, flush rounded
  PiP, Shorts stack. HyperFrames overlays composite ON TOP of this base.

## Body motion is a full-frame OPAQUE CUTAWAY — never a transparent text overlay on the screen

The iteration-2 defect: body motion was a semi-transparent colorkey overlay riding on top of the live
screen recording (faint red text bleeding over the repo — 1:40, 1:56). **Fixed.** On the Long body,
motion is now a **full-frame opaque cutaway that REPLACES the screen** for its beat:

- Author the beat with `"mode":"cutaway"` (or render with `--cutaway`). `scripts/motion_render.py`
  renders it on an **opaque `#0a0a0a` threadify-fc ground** (no colorkey), with a ~150ms fade in/out,
  as a **standalone, video-only segment**. The timeline **overlays it in place of the screen** for
  `[start,end]` while the narration audio keeps playing underneath — screen-proof plays clean between
  cutaways. It is NEVER colorkey-composited over the screen.
- **Transcript-anchored:** each cutaway starts at the transcript timestamp of the words it depicts, so
  the visual always matches what's being said (kills the "words don't match the visual" drift).
- The transparent-overlay path still exists for **Shorts labels only** (opaque panel card + light
  labels), not the body.

## Iconography, not text (the rule that changed) — now LINT-ENFORCED

- Lead with a **visual** of what's being said. A concept about "any model" → model logos/chips as a
  ledger; "they stole my post" → the actual post/receipt; "runs locally & free" → a laptop + lock
  icon. Text is a short label under the visual, if at all.
- **Enforced by `lint_brief` in `motion_render.py`:** on a body/cutaway brief, a `flow` node or a
  `chip` whose lead is bare text is **rejected** (non-zero exit) — supply an icon per node/chip
  (`{"icon":"swap","text":"…"}` / `{"icon":"chip","label":"…"}`). A `stat` supporting line must be a
  short label (≤5 words), not a sentence. The kicker may stay as a small mono label.
- **Show real proof when it exists.** If `source/` (or the screen capture) contains the referenced
  screenshot, composite the REAL thing. Only recreate on-brand (`receipt_print`) when no real asset
  exists.
- Never cover the picker/proof on the screen or the camera PiP. Complement the screen; don't
  duplicate what it already shows.

## Layout menu (alternate with camera cuts)

Vary the layout; don't lock one template (Tariq: "curious how it will alternate between camera
cuts"). Choose per moment:

- **Full animation (opaque cutaway)** — HTML slide fills the frame and REPLACES the screen (section
  intros, concept beats, big reveals). Opaque `#0a0a0a` ground, narration continues under it.
- **Animation + speaker PiP** — slide with the webcam in the corner (explaining a concept).
- **Speaker full** — just the talking head (personal / vulnerability beats — no motion here).
- **Screen recording** — the raw demo (walkthroughs, proof).

Cut between these on natural beats. Personal/vulnerability moments stay **speaker full** — no
animation competing with the emotion.

**On the Long, apply the menu actively (this is now enforced, not optional):**
- A **section-intro card** at every section boundary in `edit-plan.md`.
- A **HyperFrames concept slide** (icon/image-led) for each major framework, number, comparison, or
  list the narration lands on — aim for one every ~60-90s of body, not a flat screen+PiP for minutes.
- **Alternate** full-animation / animation+speaker-PiP / screen / speaker-full so it never sits on
  one template. These varied HTML layouts are the visual proof the Long is *produced*, not raw.

**On Shorts:** whenever the narration references something not on the screen panel, drop an on-brand
HyperFrames icon/image overlay for that beat (top or mid, clear of the caption strip and the face).

## Render speed (proxy-first)

Tariq's bottleneck was render time. During the self-heal loop, render everything **low-res proxy**.
Only when all gates pass do you do the single **full-res** render. This makes the ≤3 redo loop cheap.

## Small delighters

A tasteful end-card (e.g. a closing picture/frame) is welcome — Tariq liked "the little picture at
the end." Keep it subtle; it's a garnish, not a feature.
