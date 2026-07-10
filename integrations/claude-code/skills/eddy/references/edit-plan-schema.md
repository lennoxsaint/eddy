# EditPlanV3 schema

`edit-plan.json` is the host-authored editorial contract consumed by `eddy_host_submit`. It selects
source evidence; it never contains generated speech or packaging.

```json
{
  "schema_version": "edit-plan-v3",
  "source_hashes": {"camera.mp4": "<sha256>", "screen.mp4": "<sha256>"},
  "protected": [{"start": 12.4, "end": 18.2, "reason": "vulnerable pause"}],
  "editorial_review": {
    "coverage": [[0.0, 255.0]],
    "resolutions": [
      {
        "candidate_id": "repeat-a1b2c3",
        "action": "keep_variant",
        "selected_variant_id": "variant-clean",
        "reason": "The later variant is the complete clean take."
      },
      {
        "candidate_id": "gap-d4e5f6",
        "action": "tighten_gap",
        "selected_variant_id": null,
        "reason": "Unprotected silence."
      }
    ]
  },
  "body": {
    "keep": [[20.0, 140.0]],
    "drop": [[70.0, 76.0]],
    "retake_groups": [
      {
        "id": "R1",
        "selected_variant_id": "R1-clean",
        "variants": [
          {"id": "R1-false", "start": 80.0, "end": 87.0},
          {"id": "R1-clean", "start": 90.0, "end": 98.0}
        ]
      }
    ]
  },
  "hooks": [
    {"id": "proof", "rank": 1, "segments": [[140.0, 175.0]], "proof_assets": ["post.png"]},
    {"id": "speed", "rank": 2, "segments": [[180.0, 215.0]], "proof_assets": []},
    {"id": "cost", "rank": 3, "segments": [[220.0, 255.0]], "proof_assets": []}
  ],
  "shorts": [
    {
      "id": "proof-short",
      "segments": [[140.0, 170.0]],
      "drop": [[151.2, 153.8]],
      "screen_proof_segments": [[145.0, 155.0]],
      "motion_beats": [
        {"id": "proof-hook", "start": 0.0, "dur": 1.2, "layout": "stat", "value": "46K"},
        {"id": "proof-support", "start": 12.0, "dur": 1.5, "layout": "image", "label": "Receipt"}
      ]
    },
    {
      "id": "speed-short",
      "segments": [[180.0, 210.0]],
      "screen_proof_segments": [[185.0, 195.0]],
      "motion_beats": [
        {"id": "speed-hook", "start": 0.0, "dur": 1.0, "layout": "stat", "value": "FREE"},
        {"id": "speed-support", "start": 10.0, "dur": 1.5, "layout": "flow", "nodes": []}
      ]
    },
    {
      "id": "cost-short",
      "segments": [[220.0, 250.0]],
      "screen_proof_segments": [[225.0, 235.0]],
      "motion_beats": [
        {"id": "cost-hook", "start": 0.0, "dur": 1.0, "layout": "stat", "value": "$0"},
        {"id": "cost-support", "start": 9.0, "dur": 1.5, "layout": "icons", "icons": []}
      ]
    }
  ],
  "motion_beats": [
    {"id": "long-hook", "hook_id": "*", "start": 0.0, "dur": 1.5, "layout": "stat", "value": "46K"},
    {"id": "long-proof", "hook_id": "*", "start": 8.0, "dur": 1.5, "layout": "image", "label": "Proof"}
  ]
}
```

## Invariants

- Source hashes use source-relative paths and must exactly match the job's source lock.
- There is one body and exactly three unique hooks ranked `1`, `2`, and `3`.
- The rank-1 hook creates the Primary Long; ranks 2 and 3 create Alternate Longs.
- Every range is source time with `0 <= start < end`.
- `editorial_review.coverage` spans every transcript chunk and every ledger candidate has exactly one
  resolution with a reason. The default resolution keeps the last complete clean variant.
- Protected moments survive every long, but protection cannot preserve more than 0.8s of silence.
- Provide 3–5 unique, quality-gated Short candidates. If three do not clear the bar, the plan blocks.
- A Short may declare source-time `drop` ranges for retakes that occur only inside that Short. Each
  drop must stay inside its declared source segments, cannot erase the whole candidate or protected
  content, and is merged with shared-body drops before the camera splice.
- Every dual-source Short maps at least 25% of its duration to raw screen proof and declares at least
  two motion beats: an opening hook beat by 2s and a later proof beat.
- Each long hook receives at least two host-authored HyperFrames beats through `motion_beats`.
- Eddy resolves each motion beat against the real base frame into a compact contextual panel. Host
  intent supplies the message and visual layout; Eddy owns safe placement, PiP/face/caption/footer
  exclusions, light/dark environment treatment, and rendered-pixel collision proof.
- Short caption timing comes from the final splice receipt and must align with a fresh delivered-media
  transcript. Source-time or uniformly synthesized word timings cannot pass.
- Titles, descriptions, chapters, thumbnails, publishing fields, and arbitrary timestamps outside the
  source lock are rejected.
