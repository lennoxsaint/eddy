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
  --out edited.mp4 [--gap-threshold 0.2] [--gap-target 0.1] [--xfade 0.06]
```
`cutlist.json`: `{"keep":[[s,e],...], "sacred":[[s,e],...], "gap_tighten":{"threshold":0.2,"target":0.1}}`.
Writes `edited.segments.json` (receipt: exact sub-segments used).

## 3. Descript Studio Sound (audio only)

```
python3 scripts/descript_studio_sound.py --in edited.mp4 --out edited_ss.mp4 [--intensity 100] [--work ./audio]
# audio-only variant (input already a WAV):
python3 scripts/descript_studio_sound.py --in edited.wav --out clean.m4a --audio-only
```
Extract WAV → Studio Sound → parity (±1%/1s) → mux back. Exit 2 = key missing, 3 = parity failed.

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
  [--source-audio source.wav] [--expect-w 1920] [--expect-h 1080]
```
Prints a JSON verdict `{pass, gates:[...]}`. Exit 1 = a gate failed. Model rubrics
(hook/cohesion/gutting) are judged separately by you.

## Motion + captions (existing skills, via CLI)

- HTML motion (hook, section cards, concept slides): `npx hyperframes …` (see the `hyperframes` skill).
- Karaoke: the `embedded-captions` skill, `anchor` identity (clean, verbatim — not chaotic).
