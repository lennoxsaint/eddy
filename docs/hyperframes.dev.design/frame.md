---
primitive: frame.md
owner: Eddy
precedence: 1
canvas: "1920x1080"
contract: "normative video-frame design system"
---

# frame.md

`frame.md` is Eddy's highest-priority motion design contract. When `frame.md`,
`design.md`, and `DESIGN.md` disagree, `frame.md` wins.

Use it to define:

- canvas, color tokens, typeface, stroke weights, safe zones, and forbidden moves
- product-specific visual language
- collision boundaries for face, captions, browser chrome, proof UI, and text the viewer must read
- acceptable transitions: fade, zoom, blur bridge, kinetic type, liquid/glass, highlight sweeps
- proof requirements before compositing

Every premium motion layer must copy the selected HyperFrames references into the run folder and
write `copied-assets-manifest.json`. Do not hotlink `/tmp`, a remote repo, or another local checkout.
