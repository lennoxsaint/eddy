# Edit-plan schema — the human-readable EDL

`edit-plan.md` is the single intermediate artifact: a sectioned, timestamped beat map that doubles
as the edit decision list and the receipt. Format modeled on Tariq's talk edit
(`## 2. Section — [mm:ss–mm:ss] · slides/visuals`).

## Structure

```markdown
# Edit plan — <slug>

- source: <camera file> + <screen file> (dual-source) | <camera file> (talking-head)
- raw duration: <mm:ss> · transcript: <path> · target: <N min or "none">
- packaging target: "<inferred or read title>" / thumbnail: <direction>

## Hook — [00:00–00:XX]
- cold open: keep beat #<id> word-for-word — "<first line verbatim>"
- bridge: tease reveals → #<id>, #<id>, #<id>
- motion: <HyperFrames brief for first 60s>
- alt cold-opens: A = #<id> · B = #<id>

## 1. <Section title> — [00:XX–0X:XX] · <visual/layout note>
- beat #<id> [mm:ss–mm:ss] keep — "<summary>"
- beat #<id> [mm:ss–mm:ss] duplicate of #<id> → cut (reason)
- beat #<id> [mm:ss–mm:ss] tangent → cut (reason)   ← also goes in spot-check.md
- retake-group R#<n> [takes at mm:ss, mm:ss] → keep last (mm:ss)
- SACRED [mm:ss–mm:ss] — vulnerability moment, do not touch

## 2. <Section title> — [0X:XX–0X:XX] · <visual note>
...

## Shorts (3-5)
- short 1: moment #<id> [mm:ss–mm:ss] — hook: "<line>"
- short 2: ...

## Cut list (executed by splice.py)
- keep: [<start>,<end>], [<start>,<end>], ...   (in source seconds)
- gap-tighten: gaps >0.2s → 0.1s, except sacred spans [<start>,<end>], ...
```

## Rules

- Every beat has an `id`, a source-timestamp span, a class, and a one-line summary.
- Section headers carry a timestamp range and a visual/layout note (drives the motion layer).
- The **Cut list** at the bottom is the machine-consumable output: kept source spans + the
  gap-tighten policy + the sacred-span exemptions. `scripts/splice.py` consumes exactly this.
- `keep` beats and `SACRED` spans are the contract `scripts/verify.py` checks against the final cut.
