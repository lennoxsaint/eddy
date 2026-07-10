# Commands — exact CLI for every frozen helper

Run scripts from the skill's `scripts/` dir. Paths below are relative to a run folder you choose
(e.g. `~/content-pipeline/<slug>/`). All scripts print one JSON receipt line on success and exit
non-zero on failure. Use `python3`.

## Env

- `DESCRIPT_API_KEY` — required for Studio Sound (already in `~/.zshenv`). Auth = `Bearer <key>`.
- `EDDY_FAKE_DESCRIPT=1` — dev-only offline audio approximation; NEVER ship its output.

## 1. Transcribe (WhisperX → word-level JSON)

```
python3 scripts/transcribe.py --in <camera_or_mixed>.mp4 --out transcript.json [--model large-v3] [--lang en]
```
Output: `{language, duration, words:[{word,start,end,score}], segments:[...]}`.

## 2. Splice (execute the cut list + tighten gaps)

```
python3 scripts/splice.py --in <source>.mp4 --words transcript.json --cutlist cutlist.json \
  --out edited.mp4 [--gap-threshold 0.2] [--gap-target 0.1] [--xfade 0.012] [--silence-db -30] \
  [--scale 1920x1080] [--segments prior.segments.json]
```
`cutlist.json`: `{"keep":[[s,e],...], "sacred":[[s,e],...], "gap_tighten":{"threshold":0.2,"target":0.1}}`.
Writes `edited.segments.json` (receipt: exact sub-segments used).
**Dead air** is removed via ffmpeg `silencedetect` (real audio energy) as well as inter-word gaps, so
a long silence with NO transcribed words is still tightened (fixes the survivors). `--silence-db` is
the noise floor. `--xfade` (~12ms) is a length-preserving de-click fade at each join (kills the cut
click without desyncing audio from the frame-select'd video).
`--scale WxH` downscales each cut segment during the splice — use it to cut a **4K screen track
directly at 1080p** (lighter/safer encode; the composite scales to 1080p anyway).
**Co-splicing a screen track:** splice the **camera first** (it has audio → it owns the
silence-driven cut and writes `.segments.json`), then splice the screen with
`--segments <camera>.segments.json` so it reuses the identical sub-segments and stays frame-synced
(the screen has no audio to silencedetect, so it must NOT recompute).

## 3. Descript Studio Sound (audio only)

```
python3 scripts/descript_studio_sound.py --in edited.mp4 --out edited_ss.mp4 [--intensity 100] [--work ./audio]
# audio-only variant (input already a WAV):
python3 scripts/descript_studio_sound.py --in edited.wav --out clean.m4a --audio-only
```
Extract WAV → Studio Sound → parity (±1%/1s) → calibrated Effect-Survival Gate → mux back.
Exit 2 = key missing; exit 3 = parity or effect-survival failure.

## 4. Composite (rounded-corner layout + Shorts)

```
# YouTube long (16:9): screen base + rounded webcam PiP bottom-right
python3 scripts/composite_render.py long --screen screen.mp4 --camera cam.mp4 --out long.mp4 [--proxy] [--bg 0x0b0b0b]
# talking-head long (camera only)
python3 scripts/composite_render.py th --camera cam.mp4 --out long.mp4 --w 1920 --h 1080 [--proxy]
# Short (dual-source stack)   |   Short (talking-head)
python3 scripts/composite_render.py short --face cam.mp4 --screen screen.mp4 --out short.mp4 [--proxy]
python3 scripts/composite_render.py short --face cam.mp4 --out short.mp4 [--proxy]
```
`--proxy` = fast half-res draft (use during the ≤3 self-heal loop; full-res only at the end).
Karaoke is NOT burned here — add it with `embedded-captions` `anchor`.

## 5. Verify (deterministic gates)

```
python3 scripts/verify.py --final long.mp4 [--segments edited.segments.json] [--plan edit-plan.json] \
  [--source-audio source.wav] [--expect-w 1920] [--expect-h 1080] \
  [--final-words final.words.json] [--max-deadair 1.5] [--min-speech-ratio 0.45] [--silence-db -30]
```
Prints a JSON verdict `{pass, gates:[...]}`. Exit 1 = a gate failed. New gates:
`max_internal_silence_ok` (silencedetect the rendered file — catches dead air a cut missed),
`speech_ratio_ok`, and `retake_repeat_scan` (needs `--final-words`: **re-transcribe the final render**
with `transcribe.py`, pass its words here; flags adjacent duplicate phrases = leftover retakes).
**Run this on every long AND every Short.** Model rubrics (hook/cohesion/gutting) are judged by you.

## 6. Karaoke (Shorts caption strip)

```
python3 scripts/karaoke_ass.py --transcript short.words.json --out short.ass \
  --play-w 1080 --play-h 1920 --y 1155 --font-size 68 --max-words 4 --uppercase \
  --burn --in short.mp4 --video-out short_cap.mp4
```
Self-contained per-word karaoke (cyan current word / white spoken / dim upcoming, `layout-constants.md`
style). `--transcript` = word timings of the **edited** short (re-transcribe the composited short first,
because splicing shifts word times). Position `--y` in the Shorts caption strip (1080–1230 → center 1155).

## 7. HyperFrames motion — the DEFAULT engine (iconography-forward, threadify-fc)

```
# render an on-brand overlay AND composite it onto a base (keyed alpha; base continues after):
python3 scripts/motion_render.py --run-dir work/mo-hook --hook "Codex with any model — free" \
  --out work/mo-hook/overlay.mp4 --duration 60 \
  --composite-over work/long_composite.mp4 --composite-out work/long_motion.mp4
# overlay only (composite later):        add --portrait for a 1080x1920 Short card
python3 scripts/motion_render.py --run-dir work/mo1 --hook "..." --out overlay.mp4 [--portrait] [--duration N]
# GPU-free dry run to validate mechanics: add --fake
```
Uses the bundled threadify-fc identity and supported `npx hyperframes` lint → validate → inspect →
render contract. It has no dependency on a separate Eddy checkout. Output is a black-bg MP4 keyed
to alpha and composited over the base.
- **Machine safety (hard rule):** the real render drives a headless Chromium via `npx hyperframes`.
  **Never run it during an ffmpeg encode** — render motion first, composite after. Validate with
  `--fake` first (zero GPU). Proxy in the loop; only the final pass is full-res.
- Feed the hook/beat text that represents the **spoken words as a visual** (icon/image-led), never a
  restated caption. Never cover the on-screen picker/proof or the camera PiP.

## 7b. ffmpeg type motion — FALLBACK ONLY (`motion_type.py`)

```
python3 scripts/motion_type.py --in in.mp4 --out out.mp4 --beats beats.json \
  --font assets/fonts/Montserrat.ttf [--fade 0.25] [--audio copy|reencode]
```
The old flat-type engine. Use ONLY when HyperFrames is unavailable/erroring, or for a trivial
one-word label where a full HTML render is overkill. No longer the default or the aesthetic target.
`beats.json`: `[{"text","start","end","size","color":"cyan|white|0xRRGGBB","x","y","align":"l|c",...}]`.

## Long-form captions (existing skill, via CLI)

- Talking-head long-form karaoke: `embedded-captions` `anchor` identity (matts the person). Does NOT fit
  a screen-share composite or the Shorts split-stack — use `scripts/karaoke_ass.py` for those.
