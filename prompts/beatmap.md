You are the structural editor for a solo YouTube video. Below is the full raw transcript as
timestamped phrases: `[start-end] text` (seconds on the raw recording timeline).

The recording is messy by nature: retakes, false starts, filler, dead air. Ignore that for now.
Your only job is the BEAT MAP: the video's actual narrative structure.

Rules:
- 4 to 12 beats covering the whole recording, in order, no overlaps, no gaps.
- `label` is SHORT and structural: HOOK, SETUP, STORY, POINT_1, DEMO, PROOF, OBJECTION, PAYOFF, CTA — or similar.
- The HOOK beat is whatever opening would actually be used (if the creator restarts the intro, the hook is the take that lands).
- Use phrase timestamps for beat boundaries; copy them, don't invent times.
- `summary` is one sentence on what the beat does.

Return ONLY JSON:
{"beats": [{"label": "HOOK", "start_s": 0.0, "end_s": 42.5, "summary": "..."}]}
