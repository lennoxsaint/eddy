---
version: v5
name: Threadify FC
chrome: brand
chrome_label: "THREADIFY"
tagline: >
  The gold standard — Threadify × Full Circle launch-video DNA: register-disciplined dark/fire
  frames, strike-swaps, receipt prints, device showcases, constrained-physics CTAs, FWED moments.
when_to_pick: >
  Threadify-related videos by default, and any video that needs the launch-video energy: proof
  that accumulates, problem words struck through and replaced, a CTA the cursor actually presses.
  Built first and perfected first; every other identity calibrates against this one.
grounded_in:
  - ~/Developer/threadify-launch-video (9-scene 16:9 master, 124 BPM velocity grammar)
  - ~/full-circle/launch/videos/fc5-launch (register discipline, receipt triptych, RUBRIC loop)
colors:
  ground: "#0a0a0a"
  panel: "#141414"
  panel-edge: "#282626"
  accent: "#FF0000"
  accent2: "#e3160d"
  text: "#fafafa"
  muted: "#737373"
  cream: "#fffdf8"
  paper: "#fdfaf1"
  ink: "#141414"
fonts:
  display: "Avenir Next"
  display_fallback: "Inter Variable"
  mono: "Space Mono"
registers:
  dark:
    ground: "#0a0a0a"
    text: "#fafafa"
    accent: "#FF0000"
    note: default — near-black canvas, off-white type, Threadify red as the one voltage
  fire:
    ground: "#e3160d"
    text: "#141414"
    highlight: "#fffdf8"
    note: the FC5 statement register — ink type on fire-red; never mixed with dark in one scene
signature_archetypes:
  - strike_swap
  - receipt_print
  - device_showcase
  - card_handoff
  - counter_scale
  - cursor_press
  - type_slam
motion:
  preset: snappy
  transition_default: zoom_through
  seam_palette: [zoom_through, push_slide, wipe_handoff, crossfade]
  character: >
    Launch-video velocity: power3.out slams that settle with confidence, hard editorial swaps
    (0.08s, no ease), glow as a consequence of events, exactly one back.out pop reserved for the
    CTA press. Elements hand off — a card flies into the terminal, the strike bar causes the swap,
    the cursor's arrival IS the press.
icon:
  stroke: 2.2
  draw: true
---

# Threadify FC — frame spec (the gold standard)

The unit is the frame (1920×1080; 9:16 documented). Two registers, never mixed inside a scene:
**dark** (cream-white type on near-black, Threadify red voltage) and **fire** (ink type on FC
fire-red, cream highlights). Flat plane: 1px hairlines (`#282626` on dark, 20% ink on fire), no
box-shadows; depth comes from radial glow layers behind key cards and the grain/vignette stack.

## Brand atoms
- **Needle mark** (`assets/threadify-needle.png`) — the real needle-and-thread logo. Lives in the
  chrome bug top-left; the morph target for `morph_cta`.
- **FWED** (`assets/*-keyed.png`: hero, think, agent, receipt, done, stuck) — the red pixel-art
  teddy. At most ONE appearance per render, on the emotional payoff beat, via `data.mascot`
  (e.g. `"done-keyed.png"`): entrance pop + two settle hops. Crisp downscale, never upscaled.
- **FC ring** (`assets/fc-ring.png`) — the Full Circle ring; available as a secondary bug.

## Typography
- Display: **Avenir Next 900 lowercase**, tracking −0.03/−0.04em (FC5's authority signal), falling
  back to bundled **Inter Variable 900** for portability. Massive scale, negative tracking.
- Chrome/labels: **Space Mono** uppercase, 0.14em tracking. Prices, URLs, receipts, tool rows.

## Motion (character: snappy — launch-video velocity)
Entrances power3/power4.out and BLUR-MASKED (blur 14px → 0); exits power2/3.in, faster than
entrances. Hard swaps cut in 0.08s with no ease. Glow envelopes attack to 0.85 and settle at 0.45
— never a static glow. The single back.out(1.8) lives in `cursor_press`. Seams: zoom-through,
push-slide, wipe-handoff, crossfade — never the same seam twice in a row.

## Signature scenes
- **strike_swap** — problem word struck by a physical bar, hard-swapped to the solution (likes →
  leads). The check/cross marks trade places in lockstep.
- **receipt_print** (register: dark, paper `#fdfaf1`) — thermal receipts with perforated teeth
  print top→bottom on VO beats; the red underline draws under the figure; receipts accumulate.
- **device_showcase + card_handoff** — a Claude/Codex-credible dark window persists via `surface`;
  an intent card flies INTO it; results print as consequences.
- **cursor_press** — the CTA: pill pops (the one playful beat), cursor travel == press, glow
  blooms from the press, FWED `done` confirms.
- **fire statement** (register: fire) — one ink-on-fire type_slam as the emotional stamp.

## Aspect-ratio behaviour
16:9 primary. 9:16: safe-zone content upper-third biased, pill CTA inside the caption keep-out,
FWED never dips into the bottom 17%.

## Negative list (enforced by the engine + rubric)
No elastic/bounce beyond the one sanctioned pop, no purple-blue AI gradients, no bokeh/particle
fields, no box-shadows, no second sans, no static glows, no invented numbers.
