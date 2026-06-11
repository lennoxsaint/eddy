# Lennox Shorts Rendering Standard

Use this reference when rendering or directing YouTube Shorts from Lennox camera + screen recordings. This standard captures the approved `Clients Hunt You v3` result.

## Default Layout

- Export `1080x1920` vertical MP4 with audio.
- Background: deep navy or equivalent dark neutral.
- Top panel: use the real camera source, not a crop of an already-composited longform export. The face-cam should be a large clean square/near-square panel, centered, balanced around head, headphones, shoulders, and upper chest.
- Panel corners: use a polished rounded-square crop when the approved style uses a square headshot. Do not switch to hard corners, circles, red frames, or a different crop language without explicit approval.
- Caption zone: directly under the face-cam, centered, no overlap with face or screen. Captions should be large enough to feel like the approved Descript-style preview, not tiny subtitle text.
- Bottom panel: use the real screen/proof source, fit to full source width with padding as needed, matching the face panel width as closely as practical. Do not zoom/crop aggressively unless the screen content is unreadable.
- The approved reference is a clean stacked layout: large camera on top, karaoke captions immediately below, screen/proof panel below. If a render makes the camera or screen look like small thumbnails, it fails visual QA.
- Exact dimensions from a project style lock override these defaults. If a user-approved style lock says `930x930` rounded-square headshot, blue karaoke captions, and full-width proof panel, use those exact constants until the user explicitly changes them.

## Caption Behavior

- Captions are mandatory on every Short.
- Use transcript word timings when available.
- Display short word groups, usually 3-6 words.
- Already-spoken words: bright/emboldened.
- Current word: blue highlight behind the word with strong white text.
- Future words: dim/silhouetted but still readable.
- Captions must be visible in QA frames; a Short with missing captions fails QA.
- For Lennox Shorts, keep the approved blue current-word karaoke highlight unless Yazzy or Lennox explicitly says Shorts captions must use another color. Long-form motion-graphics direction such as white/black/red does not automatically override the Shorts caption style.

## Source Recovery

- Prefer real camera, screen, and clean audio tracks from the target video. Do not use same-named files from `Downloads` or `source/raw` without verifying duration and visual content against the Descript target.
- If the target project is in Descript and separate local sources are missing, use Descript's Timeline export with `Final Cut Pro X (.fcpxml)` and `Include media files in export` enabled. Grant local save access, wait for both camera and screen MP4s to finish, then copy the completed media into a clearly named source folder for the exact target composition or timeline.
- A browser/local permission sheet may create an empty export folder first. Treat `.crswap` or Descript app-storage temp files as incomplete until the final MP4 appears and `ffprobe` succeeds.
- Validate source identity before rendering: target project/video name, composition or timeline id when available, expected duration range, camera resolution, screen resolution, and spot-check frames. Same-named files with the wrong duration are traps, not acceptable sources.
- If a project has multiple Descript compositions or prior exports, write a source-lock receipt before rendering. The receipt must name the required composition/timeline id, forbidden stale ids or folders, expected duration, and source media paths. Fail closed if any render script points at the wrong source.

## Edit Standard

- Run a transcript timing audit before rendering.
- Split broad candidate ranges into phrase-level keep segments.
- Remove obvious word gaps, long pauses, false starts, repeated takes, filler setup, and dead-air transitions.
- Preserve natural micro-pauses when they make the delivery human.
- Keep the final/best take by default unless an earlier take is clearly sharper.
- Leave audio-safe handles around phrase cuts so first and last words are not clipped. Transcript timings are approximate; do not place cuts directly on Whisper word boundaries.
- Hard-fail any planned phrase boundary with less than `0.10s` before the first selected word or after the last selected word unless the adjacent word is intentionally included. Manually review any boundary under `0.12s`.
- Prefer fewer, safer phrase cuts over over-tight microcuts that risk shaving syllables.
- End every Short on a complete sentence and complete thought. Do not end on a setup question, connector, dragged-in next word, or line whose answer continues immediately after the cut.
- Treat `Hook for Short`, `book4short`, `book for short`, and close transcription variants as Short markers, not final caption copy unless the user explicitly wants them retained.
- For the long-form edit, marker removal must include a flow check on the first sentence after the marker. If that sentence only functions as a standalone Short hook and does not connect smoothly to the surrounding long-form argument, remove it from the long edit while still using it as a Short candidate when appropriate.
- If the listed Short hook does not exist as a clean spoken phrase, do not fabricate it. Render only exact or safely adjacent transcript-backed candidates, and mark missing/too-short candidates in the Shorts manifest.

## Approval And Rollback

- Use a sample-first loop: render one Short, generate MP4 plus contact/contact-sheet frames, then wait for feedback before batch rendering.
- Sample approval is source-specific. If the sample uses separate camera/screen files, do not treat a later flattened-export render as equivalent.
- Sample approval is also style-specific. Do not change caption colors, headshot shape, crop geometry, border treatment, or source class between the approved sample and the batch unless the user explicitly approves that change.
- If the target video's separate camera/screen media is missing, stop and request/export the source media or Descript timeline export with included media before rendering a full batch. Do not ship a cropped flattened export as a substitute for the approved layout.
- Do not overwrite previous exports. New visual/edit passes must write to a fresh output folder.
- When feedback changes future behavior, log it in `shorts-feedback-ledger.md` with status `accepted`.

## QA Gate

Before calling a batch complete:

- `ffprobe` each MP4 for `1080x1920`, duration, and audio/video streams.
- Decode audio and video samples with `ffmpeg`.
- Generate a contact sheet for every Short.
- Inspect for missing captions, bad face crop, unreadable screen crop, clipped words, obvious word gaps, retake leftovers, layout collisions, and source/layout drift from the approved reference.
- Fail visual QA if camera or screen panels were derived from a flattened longform export when separate source media was required for the approved layout.
- Write an audio-boundary ledger for every planned phrase cut: first word, last word, pre-word handle, post-word handle, and hard-fail/review status.
- Write a sentence-final QA ledger for every rendered Short: exact final selected line, raw transcript words immediately after the cut, and pass/fail on complete sentence + complete thought.
- Run final MP4 silence/decode QA, including start, internal, and end dead-air checks; map any flagged silence back to transcript timings and fix before review. When de-silencing final MP4s, remove only the center of detected low-audio spans and leave handles on both sides so word tails survive.
- Generate a tail-ending QA reel from the final rendered MP4s so all endings can be reviewed quickly in sequence.
- Generate a join-boundary QA reel around internal cut points for batches that previously had clipped-word or dead-air feedback.
