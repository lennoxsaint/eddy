# EditPlanV3 schema

`edit-plan.json` is the host-authored editorial contract consumed by `eddy_host_submit`. It selects
source evidence; it never contains generated speech or packaging.

```json
{
  "schema_version": "edit-plan-v3",
  "source_hashes": {"camera.mp4": "<sha256>"},
  "protected": [{"start": 12.4, "end": 18.2, "reason": "vulnerable pause"}],
  "body": {
    "keep": [[20.0, 140.0]],
    "drop": [[70.0, 76.0]],
    "retake_groups": [{"id": "R1", "keep": [90.0, 98.0], "drop": [[80.0, 87.0]]}]
  },
  "hooks": [
    {"id": "proof", "rank": 1, "segments": [[140.0, 175.0]], "proof_assets": ["post.png"]},
    {"id": "speed", "rank": 2, "segments": [[180.0, 215.0]], "proof_assets": []},
    {"id": "cost", "rank": 3, "segments": [[220.0, 255.0]], "proof_assets": []}
  ],
  "shorts": [
    {"id": "proof-short", "segments": [[140.0, 170.0]]},
    {"id": "speed-short", "segments": [[180.0, 210.0]]},
    {"id": "cost-short", "segments": [[220.0, 250.0]]}
  ],
  "motion_beats": [{"hook_id": "proof", "start": 0.0, "end": 4.0, "kind": "proof"}]
}
```

## Invariants

- Source hashes use source-relative paths and must exactly match the job's source lock.
- There is one body and exactly three unique hooks ranked `1`, `2`, and `3`.
- The rank-1 hook creates the Primary Long; ranks 2 and 3 create Alternate Longs.
- Every range is source time with `0 <= start < end`.
- Protected moments survive every long.
- Provide 3–5 unique, quality-gated Short candidates. If three do not clear the bar, the plan blocks.
- Titles, descriptions, chapters, thumbnails, publishing fields, and arbitrary timestamps outside the
  source lock are rejected.
