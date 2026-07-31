---
name: eddy
description: >-
  Use Eddy to turn attached raw footage into a proof-gated YouTube primary long, two alternate-hook
  longs sharing the same body, and only genuinely strong Shorts. Eddy never publishes or mutates
  source media.
metadata:
  version: 3.0.0
  author: lennoxsaint
---

# Eddy

Use this skill when the user mentions Eddy, attaches raw footage, or asks for a YouTube edit. Call
the product **Eddy** in normal conversation; plugin namespaces and version labels are routing details.

The host model is Eddy's editorial brain. Eddy's thin runtime owns source locks, asynchronous stage
execution, deterministic mechanics, receipts, cancellation, and proof gates.

## Product contract

For a normal "edit this" request, Eddy produces videos only:

- one ranked primary long;
- two complete alternate-hook longs that reuse the identical body edit;
- 3-5 Shorts only when that many standalone moments pass every required gate;
- transcript, edit plan, spot checks, deterministic QA, and receipts.

Titles, descriptions, chapters, thumbnails, uploads, publishing, sending, and scheduling are outside
v3.0. Never mutate, move, delete, upload, or publish source media.

For the owner channel, resolve `lennox-professional-youtube-v2` automatically unless the run
explicitly selects another profile. Generic creators continue to use `creator_good_v1`. Normal Eddy
runs are single-editor workflows and never launch a bake-off. Only an explicit bake-off request may
hand Eddy's frozen contract bundle to the standalone `video-edit-bakeoff` skill.

Treat 0-3 seconds and 0-30 seconds as hard-gated Viewer-Leverage Windows and the first repair
priority, without weakening the body. Frame one moves, the strongest honest money shot lands by 3s,
real proof lands by 10s, and stakes plus route are legible by 30s.

Use `edit-plan-v3.6` when a Strategy Profile V7 Opening Edit Blueprint is present; otherwise use
`edit-plan-v3.5`. V3.6 retains the v3.5 proof system and binds the pre-production
`opening-edit-blueprint-v2` as delivered choreography through
second 60. Every planned opening scene must map to a delivered scene, and every substantive
deviation needs a reason and proof receipt. Legacy plans through v3.5 remain readable, but cannot
claim V7 opening-blueprint delivery.

V3.6 also retains the v3.3 Sage-owned body structure and binds
`contracts/contract-bundle.json`, `design.md`, landscape `frame.md`, portrait `shorts/frame.md`,
the selected quality profile, verified Project Fact Brief, HyperFrames v0.7.3 doctrine, Studio Sound
lineage, audio plan, grade plan, caption policy, correction evals, independent-verifier contract,
and 100-point rubric. Host packets use `eddy-host-packet-v3.2`; bundles use
`eddy-contract-bundle-v2`. Legacy plans through v3.4 remain readable but cannot claim the v2
Lennox-profile proof state.

HyperFrames owns full-frame composition. Use talking head as the human anchor, real screen
recording for product action and proof, and authored mental models when a concept, relationship, or
result is clearer than the recording. Available layouts include full speaker, all four PiP corners,
vertical speaker left/right, embedded split left/right, speaker plus mental model, proof canvas, and
portrait speaker-top/screen-bottom. Every layout change, zoom, transition, and motion beat needs a
communication job. Reject automated drift and filler punch-ins.

Openings need 8-12 meaningful changes inside 30s and at least three layout states. In V7 projects,
those changes inherit the blueprint's communication jobs: each beat names the claim or proof it
carries, the viewer question it opens or closes, its evidence authority, and why a state change is
needed. The exact `3/10/30` deadlines and `8-12` cadence are locked; style, geometry, typography,
transition treatment, and motion language remain flexible. Long bodies must
change visual state at least every 12s; holds beyond 8s require a semantic reason. Shorts use the
same 3s opening deadline and then change state every 4-8s. Never repeat a layout more than twice
without an uninterrupted-proof reason. Evidence authority is explicit and ordered: raw source,
supplied asset, pixel-faithful demo, diagram, then clearly framed metaphor.

Preserve every unique substantive beat. Never gut a long recording into a summary clip, remove a
protected or vulnerable moment, regenerate speech, overdub the speaker, or rewrite the opening line.
Remove genuine retakes with last-take bias, remove dead air, and tighten ordinary gaps without
clipping word onsets or compressing protected pauses.

## Proof states

A **Proof-Gated Candidate Awaiting Owner Taste** has every mandatory objective gate green, all final
outputs fully watched and heard by an independent no-edit verifier, and zero objective open items.
Only this state may populate `final/`. It is not owner approval and must be reported exactly as
`proof_gated_candidate_awaiting_owner_taste`.

A **Blocked Attempt** is a playable inspection artifact with exact blockers and receipts. Complete
at least three full watch/critique/repair passes, then keep changing repair strategy until every
evidenced point is green or an exact external or technical blocker remains. Keep every red attempt
under `quarantine/attempt-<n>/`; never promote it into `final/` or call it ship-ready.

A proof-gated candidate may be reopened only by `owner-verdict-v2` with
`verdict: changes_requested`; Eddy moves that exact candidate to its numbered quarantine attempt
before accepting the repaired host plan.

Do not claim Eddy is safe to publish without human review until the repository trust ledger records
five owner-approved dogfood runs with no unresolved critical failures. Before that unlock, call green
outputs proof-gated candidates.

## Default workflow

1. Resolve the attached local file or folder. If it cannot be resolved, stop with
   `attached_source_unresolved`; never guess.
2. Call `eddy_edit_options(source=<path>, format="youtube")`. If there is one runnable path, start it
   without asking. If a material route choice remains, show only runnable options with privacy, cost,
   and quality tradeoffs.
3. Call `eddy_edit_start(...)`, optionally with explicit `profile_id` and `project_brief`, then poll
   until `awaiting_host_plan`. Eddy validates or derives a restrictive Project Fact Brief and creates
   and hashes the design contracts before host planning. Missing essential facts block with an exact
   pickup; never guess or render a placeholder.
4. Call `eddy_host_packet(job_id=...)`. Review every transcript chunk and resolve every Editorial
   Review Ledger item. Use its source hashes, typed retake variants, protected moments, proof assets,
   screen-proof candidates, motion requirements, and prior repair evidence to author `EditPlanV3`.
5. Author the v3.6 body contract, cut-integrity plan, factual proof plan, audio plan, grade plan,
   caption policy, production review, and choreography against the packet's frozen bundle. If the
   packet carries an Opening Edit Blueprint, map every planned scene through second 60 and record
   every approved deviation with a hash-bound receipt. Then call
   `eddy_host_submit(job_id=..., payload=<EditPlanV3>)`. Repair validation errors rather than
   bypassing them. Eddy auto-selects a clear, certain opening leader; when the top two are within
   five points or uncertain, inspect `eddy_opening_candidates` and call `eddy_select_opening` with
   the reason. The selected opening becomes `long-primary.mp4`; the other two remain complete
   Alternate Longs and still reuse the same body.
6. Call `eddy_finalize(job_id=...)` and keep the same active host task moving through proxy review,
   diagnosis, repair, and rerender. Do not wait for Lennox to say “continue.” On a repeated defect,
   change strategy; on a real external or technical stop, report its exact blocker.
7. At `awaiting_independent_review`, create a fresh no-edit verifier context. It reviews repaired
   intervals and adjacent joins, then fully watches and listens to all three final Longs and every
   final Short. Submit the five hash-bound review artifacts with `eddy_submit_review`. A failed gate
   reopens repair; a green submission stops at the owner-taste state.
8. When the owner reviews an Eddy output, record `owner-verdict-v2` and its evidence with
   `eddy_record_feedback`. A rejection reopens the same run. Each generalized correction names a
   regression eval and promotion class; literal project facts stay project-specific. A passed eval
   may promote into the owner profile, while generic doctrine also requires cross-project recurrence
   or explicit owner designation.
9. If critique reveals a systemic project design defect, call `eddy_revise_design_contracts` (or
   `eddy revise-design`) with the new contract text and reason. This increments revisions,
   invalidates dependent renders, and requires adherence checks again. At owner approval, propose
   reusable corrections for profile promotion; never globalize them automatically.

If MCP tools are unavailable, continue automatically through the equivalent CLI commands; do not
make the user restart the edit:

```bash
eddy options <source>
eddy edit <source> [--profile-id <id>] [--project-brief project-fact-brief.json]
eddy packet <job-id>
eddy submit <job-id> edit-plan.json
eddy opening-candidates <job-id>
eddy select-opening <job-id> <opening-id> --reason "<evidence>"
eddy finalize <job-id>
eddy status <job-id>
eddy submit-review <job-id> verifier-submission.json
eddy repair-captions <job-id>
eddy repair-privacy <job-id> privacy-repair.json
eddy record-feedback <job-id> owner-verdict.json
eddy revise-design <job-id> design-contract-revision.json
```

## Ordered edit

1. Ingest read-only sources, record before hashes, and detect dual-source versus talking-head mode.
   When top-level media exists, it is the exclusive source set; nested `runs/`, `eddy-runs/`,
   `work/`, `final/`, cache, and quarantine artifacts are never re-ingested as raw footage.
2. Transcribe to word-level timings and measure every audio silence above 0.8 seconds. Content-hash
   every decoded audio stream, transcript, timing map, metric, caption artifact, render, and review
   input. The filename is never a cache key; changed bytes invalidate every dependent artifact.
3. Build the Editorial Review Ledger. Review every chunk; resolve every repeat, reset loop, false
   start, unfinished clause, separated retake, and long gap. Keep the last complete clean take by
   default. Intentional repetition requires a recorded reason.
4. Hunt and rank three distinct proof-carrying hook angles.
5. Build one shared body edit. Keep the final clean take by default and preserve all protected beats.
6. Compile all body drops, non-selected retake variants, hook removals, and Short removals into
   explicit sample-exact splices. When transcript timestamps conflict with waveform or energy
   evidence, audio evidence controls the cut. Preserve leading phonemes, terminal consonants, and
   word endings; use sequence-search parity instead of guessed offsets. Tighten gaps above 0.2s to
   0.1s, cap unprotected delivered gaps at 0.28s, and protect declared deliberate pauses. A new shot
   must meet speech within two frames unless the plan names a protected exception. For an
   owner-locked standalone V3.6 bake-off opening, set `preserve_audio_timing: true`; never combine
   that flag with a drop inside the span, and never append the same protected body after the hook.
7. Composite the full-frame screen and rounded camera treatment, or the talking-head layout.
8. Compile the hash-bound frame and semantic scenes into one paused, seek-safe HyperFrames timeline.
   For V7 projects, treat the Opening Edit Blueprint as the pre-recorded editorial intent: preserve
   each scene's communication job and evidence requirement, while adapting visual style to the real
   footage. A missing scene, an unexplained reorder, or a changed communication job is a contract
   failure, not an invitation to improvise.
   Render three independent openings, one body composition reused byte-for-byte, and portrait
   compositions for Shorts. Motion must cover its full intended segment: frozen tails, one-frame
   flashes, accidental still endings, and broken boundaries fail. Layout changes follow the spoken
   argument; camera geometry and real proof are part of the composition. Use hard cuts by default,
   continuation crossfades only for continuity, semantic pushes or scale matches when meaning
   motivates them, and no more than two brand-act wipes per Long or one per Short.
9. Apply every declared hook-scoped privacy mask to the deterministic Long render. Validate its
   delivered-relative range and 1920x1080 rectangle, render it before audio work, and block the
   attempt if the redacted artifact is missing. Never alter the immutable raw source.
10. Apply real Descript Studio Sound to audio only. Require provider success, a changed project,
   private export provenance, duration parity, and a signal-changing **Effect-Survival Gate**. Keep
   echo and voice-texture scores as review diagnostics, not false promotion vetoes. If the effect did
   not survive an export, retry once through a fresh private render. A retryable provider failure gets
   up to three operational attempts with backoff; authentication and provenance faults fail
   immediately. Studio Sound is a file-level audio cleanup effect, not AI Speech: never create or
   require an AI Speaker or voice-consent recording. If Descript misroutes the request through its AI
   Speaker policy, issue one explicit audio-effect correction; if it repeats, block as
   `descript_studio_sound_agent_misrouted` and use the authenticated host/UI effect path. Reuse a
   prior green Studio Sound result only when the exact pre-audio MP4 hash,
   cached output hash, private provenance, and effect-survival receipt validate. Re-transcribe and QA
   cache hits normally. Never silently substitute local processing.
11. Longs have no designed captions unless the Project Fact Brief opts in. Render quality-gated
    Shorts from source-locked camera/screen inputs with progressive captions:
    prior words stay visible, the active word is highlighted, and future words stay invisible.
    Multi-speaker Shorts use stable accessible colors plus concise labels. Suppress Eddy captions
    wherever the source screen already carries readable captions. Project every word through the
    exact splice receipt, snap caption onsets after every splice/retime, and verify against a fresh
    delivered transcript.
12. Iterate with proxies; render full resolution only after the final plan is green.
13. Mix documented license-safe upbeat lo-fi music and restrained state-change SFX. Record source,
    licence, cue, purpose, and mix level. Missing suitable audio blocks; never retrieve paid audio
    silently. Grade camera footage for natural skin, exposure, white balance, and shot consistency
    while preserving screen-recording color fidelity.
14. Re-transcribe every emitted Long and Short. Complete at least three full watch/critique/repair
    passes, then perform the independent full ear/eye review. Change strategy after any failed
    attempt and continue until the mechanically recomputed rubric is 100/100 or an exact blocker
    remains. A model statement is never proof.

## Hard gates

- Source hashes are identical before and after the run.
- Exactly one shared body plan feeds all three longs; only their hook segments differ.
- The project frame hash, source refs, choreography manifest, animation map, provenance, selected
  opening, shared-body hash, and 0/1/3/10/30 comparison frames are inspectable.
- V7 plans expose the exact Opening Edit Blueprint ref/hash, benchmark library ref/hash, locked
  `3/10/30` deadlines and `8-12` cadence, a one-to-one delivered scene map through second 60, and
  explicit receipts for every deviation. No scene or communication job disappears silently.
- The body contract hash/ref, mode, route, ordered section IDs, proof-scene mapping, progress cues,
  and final payoff are inspectable. Every shared-body scene belongs to exactly one locked section.
- Every `keep` beat and protected span survives.
- Every delivered long and Short is retranscribed. No genuine retake, false start, reset loop, or
  unresolved repetition survives the delivered transcript. A deliberate callback is exempt only
  when its delivered variants match the exact source-ledger candidate reviewed as intentional.
- Word onsets are audible; gap, silence, loudness, clipping, and A/V drift gates pass.
- Sample-exact splice parity, waveform cut authority, shot-entry latency, terminal word edges, and
  delivered-stem caption onsets pass after every repair.
- Descript duration parity and Effect-Survival Gate pass on the delivered audio.
- Screen/camera geometry, transcript-synchronous caption timing, proof assets, rendered contextual
  motion placement, Shorts source/style locks, 25% source-mapped screen proof, and motion activity at
  10 fps pass.
- Burned Shorts preserve sentence-ending periods, question marks, and exclamation marks. Stray
  decorative punctuation stays suppressed, and a generated-token proof blocks missing endings.
- Motion covers each planned segment through its final frame. Frozen tails, flashes, accidental
  stills, incorrect arrows, obstructed proof, and out-of-safe-zone elements are objective failures.
- Every factual product/site view is either a pixel-faithful real capture or an evidence-bound
  reconstruction whose internal receipt says `evidence_kind: reconstructed`.
- `verifier-review.json` covers a full watch and listen of three Longs and 3-5 Shorts;
  `open-items.json` has no objective entries; optional subjective alternatives are labeled.
- A completed Short privacy repair may change pixels only: it preserves every Long hash and the
  proven Studio Sound audio stream byte-for-byte, proves each solid mask at its midpoint, and updates
  the artifact manifest before promotion.
- `spot-check.md`, `edit-plan.json`, `final/qa.json`, and `receipts.jsonl` are inspectable.

## Descript boundary

Descript is an audio service, not Eddy's editorial brain. Use either the direct API adapter or the
optional authenticated host plugin. Both must return a local audio artifact plus private-project,
composition, provider, and hash receipts, and both pass the same Effect-Survival Gate. Never expose
credentials in receipts, logs, project files, or answers.

Configure a host adapter with `EDDY_DESCRIPT_CONNECTOR`. Eddy passes `--input-wav`,
`--output-audio`, and `--receipt`. The receipt must identify `descript_host_connector`, a private
project and composition, and matching source/output SHA-256 hashes. The host owns authentication
and must not print credentials.

## Outputs

Successful objective runs write `final/long-primary.mp4`, two
`final/long-alternate-<angle>.mp4` files, `final/shorts/`, `final/transcript.md`, `final/qa.json`,
`edit-plan.json`, `project-fact-brief.json`, `verifier-review.json`, `open-items.json`,
`contracts/contract-bundle.json`, `spot-check.md`, and `receipts.jsonl`. Their state remains
`proof_gated_candidate_awaiting_owner_taste` until an explicit owner verdict. Blocked runs return
the exact blocker, quarantine path, and smallest repair action.
