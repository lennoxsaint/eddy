# EditPlanV3 schema

## Current: `edit-plan-v3.5`

V3.5 retains v3.4 and binds the Project Fact Brief, Studio Sound policy, cut-integrity
authority, factual proof routing, independent review, and owner-locked promotion:

```json
{
  "schema_version": "edit-plan-v3.5",
  "contract_bundle": {
    "schema_version": "eddy-contract-bundle-ref-v2",
    "ref": "contracts/contract-bundle.json",
    "sha256": "<sha256>"
  },
  "project_fact_brief": {
    "schema_version": "eddy-project-fact-brief-ref-v1",
    "ref": "project-fact-brief.json",
    "sha256": "<sha256>"
  },
  "audio_plan": {
    "schema_version": "eddy-audio-plan-v2",
    "music": [{"ref": "assets/audio/music.wav", "provenance": "local", "license": "owned", "cue": "0-end", "purpose": "upbeat_lofi_bed", "mix_db": -24}],
    "sfx": [{"ref": "assets/audio/click.wav", "provenance": "bundled", "license": "CC0", "cue": "12.4", "purpose": "state_change", "mix_db": -18}],
    "paid_retrieval_allowed": false,
    "studio_sound_required": true,
    "studio_sound_lineage_policy": "verified_descript_only",
    "shorts_music_policy": "purposeful_variation"
  },
  "grade_plan": {
    "schema_version": "eddy-grade-plan-v1",
    "camera_goal": "natural_skin_exposure_white_balance_consistency",
    "screen_recording_policy": "preserve_source_color_fidelity",
    "shot_checks": ["camera-a"]
  },
  "caption_policy": {
    "schema_version": "eddy-caption-policy-v2",
    "longs": {"default": "disabled", "designed_captions": false},
    "shorts": {
      "prior_words": "visible",
      "active_word": "highlighted",
      "future_words": "invisible",
      "source_caption_collision": "suppress_eddy_captions",
      "speaker_attribution": "color_plus_label",
      "speaker_colors": "design_contract_accessible_palette",
      "source_caption_intervals": {}
    }
  },
  "production_review": {
    "schema_version": "eddy-production-review-v2",
    "minimum_complete_passes": 3,
    "target_score": 100,
    "maximum_score": 100,
    "audience_performance": "NOT_RUN",
    "final_authority": "owner_taste_lock",
    "repair_policy": "change_strategy_until_green_or_exact_blocker",
    "strategy_id": "opening-proof-route-v1",
    "verifier_authority": "independent_no_edit_context",
    "verifier_edit_authority": false,
    "repair_review_policy": "repaired_intervals_and_joins_plus_full_final",
    "promotion_state": "proof_gated_candidate_awaiting_owner_taste",
    "open_items_policy": "objective_closed_subjective_optional"
  },
  "cut_integrity_plan": {
    "schema_version": "eddy-cut-integrity-plan-v1",
    "timing_authority": "waveform_energy_envelope_when_transcript_conflicts",
    "sample_exact_splices": true,
    "sequence_search_parity": true,
    "word_edge_protection": true,
    "delivered_retranscription": true,
    "shot_entry_latency_max_frames": 2,
    "protected_exception_ids": []
  },
  "proof_plan": {
    "schema_version": "eddy-proof-plan-v1",
    "real_capture_preferred": true,
    "reconstruction_receipt_required": true,
    "claims": [],
    "annotation_targets": []
  }
}
```

Readers through v3.4 remain accepted. A legacy plan cannot claim
`lennox-professional-youtube-v2` or the new owner-locked proof state.

## Legacy production contract: `edit-plan-v3.4`

V3.4 uses `eddy-contract-bundle-ref-v1`, `eddy-audio-plan-v1`,
`eddy-caption-policy-v1`, and `eddy-production-review-v1`. It remains reproducible but does not
inherit v3.5 proof semantics.

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
  "privacy_masks": [
    {
      "id": "bystander-comment",
      "hook_ids": ["proof"],
      "start": 0.0,
      "end": 18.7,
      "x": 175,
      "y": 920,
      "width": 1420,
      "height": 160,
      "color": "0x111827"
    }
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

## V3.1 Opening Proof Trailer extension

New Strategy Profile V5 projects set `schema_version` to `edit-plan-v3.1` and add:

```json
{
  "opening_visual_contract": {
    "schema_version": "1.0",
    "profile_version": 5,
    "contract_ref": "pre-production/review/opening-visual-contract.json",
    "contract_sha256": "<sha256>",
    "comparison_reel_ref": "source/eddy/opening-comparison-reel.mp4",
    "contact_sheet_ref": "source/eddy/opening-contact-sheet.png",
    "variants": [
      {
        "variant_id": "opening-proof",
        "hook_id": "proof",
        "money_shot_by_second": 3,
        "proof_by_second": 8,
        "stakes_by_second": 26,
        "meaningful_visual_beat_ids": [
          "proof-01",
          "proof-02",
          "proof-03",
          "proof-04",
          "proof-05",
          "proof-06",
          "proof-07",
          "proof-08"
        ],
        "max_unexplained_static_hold_seconds": 3.5,
        "muted_preview_status": "pass",
        "mobile_preview_status": "pass",
        "taste_review_status": "pass",
        "outlier_visual_refs": ["observed-outlier-source-id"],
        "tldraw_mode": "none"
      }
    ]
  }
}
```

The array contains one complete object for each of the three hook IDs. Every cited Long
`motion_beats` row also declares `job`, `source_kind`, `source_ref`, `meaningful_change`, and
`preview_safe: true`. At least eight cited beats must land inside 0-30 seconds for each hook, with
the first starting by second `0.04`. More than 12 is a taste warning in pre-production, not a
licence to replace meaningful change with decorative busyness. When `tldraw_mode` is
`prepared_live_reveal`, the variant also cites its `.tldr` canvas and capture plan.

## V3.2 Semantic Visual Choreography extension

Current projects set `schema_version` to `edit-plan-v3.2`, retain the v3.1 opening contract, and add
a frame contract plus three opening timelines, one shared body, and one portrait timeline per Short:

```json
{
  "frame_contract": {
    "schema_version": "eddy-project-frame-v1",
    "ref": "frame.md",
    "sha256": "<sha256>"
  },
  "visual_choreography": {
    "schema_version": "eddy-visual-choreography-v1",
    "openings": [
      {
        "id": "opening-proof",
        "hook_id": "proof",
        "ranking_signals": {
          "frame_one": 1.0,
          "money_shot": 1.0,
          "proof": 1.0,
          "stakes": 1.0,
          "muted": 1.0,
          "mobile": 0.9,
          "semantic_density": 0.9,
          "taste": 0.8
        },
        "ranking_evidence": ["opening-review-proof.json"],
        "rank_confidence": "certain",
        "scenes": [
          {
            "id": "proof-frame-one",
            "start": 0.0,
            "end": 1.4,
            "speech_anchor": "The post did forty-six thousand views",
            "semantic_job": "frame_one",
            "meaningful_change": "Open on the real post already moving into view",
            "layout": "proof_canvas",
            "evidence_authority": "supplied_asset",
            "source_refs": ["post.png"],
            "motion_verb": "reveal",
            "transition": "hard_cut",
            "cause": "The claim names the receipt.",
            "preview_safe": true
          }
        ]
      }
    ],
    "shared_body": {"id": "shared-body", "scenes": []},
    "shorts": [{"short_id": "proof-short", "scenes": []}]
  }
}
```

The abbreviated arrays above show shape only. Production plans require exactly three openings in
hook-rank order, populated shared-body scenes, and populated scenes for every Short. Allowed layouts
are `proof_canvas`, `speaker_full`, `speaker_edge_left`, `speaker_edge_right`, `speaker_pip`,
`source_screen`, `illustration_canvas`, and `special_emphasis`. Evidence authority is one of
`raw_source`, `supplied_asset`, `pixel_faithful_demo`, `diagram`, or `metaphor`.
Eddy computes the 100-point opening score from the eight normalized signals with weights
`15/20/20/10/10/10/10/5` in the order shown. `ranking_evidence` names the muted/mobile/taste review
artifacts behind those numbers; a naked subjective total is not accepted.

## V3.3 Sage-owned body structure extension

Current writers set `schema_version` to `edit-plan-v3.3`, retain the complete v3.2 frame and visual
choreography contract, and add:

```json
{
  "body_structure_contract": {
    "schema_version": "eddy-body-structure-v1",
    "source_contract_ref": "pre-production/review/script-structure-contract.json#body_structure",
    "source_contract_sha256": "<sha256>",
    "major_order_authority": "sage_locked_eddy_may_not_reorder",
    "mode": "live_test",
    "route_contract": {
      "proof": "Four operators rejected the first report.",
      "promise": "The viewer gets one consequence test.",
      "plan": "Run three increasingly consequential tests.",
      "understood_by_second": 28,
      "progress_unit": "round",
      "section_ids": ["SEC-01", "SEC-02", "SEC-03"]
    },
    "sections": [
      {
        "section_id": "SEC-01",
        "label": "The failure",
        "question": "Why did the first run fail?",
        "scene_ids": ["body-1", "body-2"],
        "proof_scene_ids": ["body-2"],
        "payoff": "The first run optimized the wrong result.",
        "viewer_action": "Name the decision before running the tool.",
        "next_loop": "Can the corrected run change a real decision?",
        "story_role": "evidence",
        "story_source_ref": "receipt:R-01"
      }
    ],
    "progress_cues": [
      {
        "after_section_id": "SEC-01",
        "scene_id": "body-3",
        "transition_card": "1 of 3: Failure",
        "spoken_callback": "The first run failed. Now the rerun has to change a decision."
      }
    ],
    "final_payoff": {
      "section_id": "SEC-03",
      "verdict": "The consequential result",
      "resulting_action": "The resulting operator action",
      "earned_cta_relationship": "Why the one CTA is earned after the result"
    }
  }
}
```

The abbreviated example shows one section and boundary. Production plans require 3-5 sections,
every shared-body scene mapped exactly once and in Sage order, at least one proof scene per section,
and one progress cue for each non-final boundary. Each shared-body scene carries the matching
`body_section_id`; the progress-cue scene is the first scene of the next section and uses
`semantic_job: reset`. Proof scenes use `raw_source`, `supplied_asset`, or `pixel_faithful_demo`.
Story roles are `none`, `evidence`, `stakes`, or `decision`; background biography is rejected.

## Invariants

- Source hashes use source-relative paths and must exactly match the job's source lock.
- There is one body and exactly three unique hooks ranked `1`, `2`, and `3`.
- The rank-1 hook creates the Primary Long; ranks 2 and 3 create Alternate Longs.
- Privacy masks are optional, have unique IDs, target existing hook IDs, use delivered-relative
  time, and stay inside the 1920x1080 Long frame. They render before Studio Sound and cannot mutate
  source media.
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
- V5 `edit-plan-v3.1` hooks receive at least eight semantic Opening Proof Trailer beats in the first
  30 seconds and pass the money-shot, proof, stakes, static-hold, muted, mobile, and taste gates.
- V3.2 opening scenes contain 8-12 meaningful changes in the first 30s, start by `0.04`, land a
  money shot by 3s, real proof by 10s, stakes by 30s, and use at least three layout states.
- V3.2 body state changes never exceed 12s; a hold over 8s needs `quiet_hold_reason`. Short changes
  never exceed 8s. Three consecutive identical layouts require an uninterrupted-proof reason.
- V3.3 preserves every v3.2 invariant and adds a body source ref/hash, route clarity by second 30,
  3-5 Sage-ordered macro sections, exact scene coverage, proof scenes, boundary cues, and a final
  payoff. `major_order_authority` has one legal value: `sage_locked_eddy_may_not_reorder`.
- Scene coverage is continuous: no unexplained black gap over 0.1s. Every opening scene is
  `preview_safe`; a `metaphor` authority explicitly identifies itself as a metaphor in `cause`.
- Opening scenes cover the complete hook cut (at least 30s), and portrait scenes cover the complete
  Short. The runtime rechecks the delivered opening is at least 29.5s after cadence tightening.
- `brand_act_wipe` is limited to two uses per Long timeline and one per Short. Prefer `hard_cut`;
  `continuation_crossfade`, `semantic_push`, and `scale_match` require a semantic cause.
- Eddy emits `opening-comparison-reel.mp4` and `opening-contact-sheet.png` for V3.1 jobs so the
  three hypotheses can be reviewed together before candidate selection.
- Eddy resolves each motion beat against the real base frame into a compact contextual panel. Host
  intent supplies the message and visual layout; Eddy owns safe placement, PiP/face/caption/footer
  exclusions, light/dark environment treatment, and rendered-pixel collision proof.
- Short caption timing comes from the final splice receipt and must align with a fresh delivered-media
  transcript. Source-time or uniformly synthesized word timings cannot pass.
- Titles, descriptions, chapters, thumbnails, publishing fields, and arbitrary timestamps outside the
  source lock are rejected.
