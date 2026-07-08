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

## Engine

- **Default — premium type in ffmpeg: `scripts/motion_type.py`.** Bold sparse type, one accent color,
  fade in/out — the mandated minimal aesthetic, done deterministically in ffmpeg. No headless browser,
  so **zero machine-panic risk** and fast to iterate (LOOK at a frame, adjust the beats, re-render in
  seconds). This is the go-to for hook benefit-beats and Shorts headlines. Rule: complement the screen
  (add the benefit framing), never duplicate what's already visible (e.g. don't re-list models the
  on-screen picker already shows), and never cover the picker/proof or the camera PiP.
- **Richer option — HTML → video: HyperFrames.** Invoke via its CLI (`npx hyperframes …`). Higher
  ceiling (real HTML layouts) but heavier + uses a headless Chromium (keep GPU off, never run its
  capture during an encode). Use only when type-in-ffmpeg genuinely isn't enough. Render proxies first.
- **Karaoke: `embedded-captions` `anchor` identity** — the clean, calm, verbatim default. This is
  the fix for Tariq's "transcription highlighting is a bit too chaotic" complaint. Never a per-word
  storm.
- **Base composite: V1 ffmpeg** (`scripts/composite_render.py`) — corners, PiP, Shorts stack.

## Layout menu (alternate with camera cuts)

Vary the layout; don't lock one template (Tariq: "curious how it will alternate between camera
cuts"). Choose per moment:

- **Full animation** — HTML slide fills the frame (section intros, big reveals).
- **Animation + speaker PiP** — slide with the webcam in the corner (explaining a concept).
- **Speaker full** — just the talking head (personal / vulnerability beats — no motion here).
- **Screen recording** — the raw demo (walkthroughs, proof).

Cut between these on natural beats. Personal/vulnerability moments stay **speaker full** — no
animation competing with the emotion.

## Render speed (proxy-first)

Tariq's bottleneck was render time. During the self-heal loop, render everything **low-res proxy**.
Only when all gates pass do you do the single **full-res** render. This makes the ≤3 redo loop cheap.

## Small delighters

A tasteful end-card (e.g. a closing picture/frame) is welcome — Tariq liked "the little picture at
the end." Keep it subtle; it's a garnish, not a feature.
