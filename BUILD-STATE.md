# Eddy GA Autonomous Build — `/goal` + `/loop` state

Live ledger for the v0.4→v1.0 march. Source of truth for "where are we" across context
compaction. Plan: `~/.claude/plans/019ead42-117d-7aa3-a28c-d8aa5ab1e87b-gri-sorted-island.md`.

## `/goal` — north star + acceptance

**GOAL:** Take Eddy from v0.3.2 to production-grade GA (v1.0): all 6 milestones implemented,
each ff-merged to `master` **locally** and tagged, full suite + fixture e2e + golden suite green,
product claims honest, human-gate batch documented.

**DONE when ALL true:**
- Milestones v0.4…v1.0 merged to `master`; tags `v0.4`…`v1.0` exist.
- `pytest` full suite green; coverage floor met; `ruff` + `mypy` clean.
- Fixture-backed `eddy run` e2e green; golden editorial suite green vs the **pinned qwen q4**.
- Claims match behavior: no network egress without logged opt-in; `--local-only`/`EDDY_OFFLINE` works;
  README/PRIVACY accurate.
- Human-gate batch (below) written here and surfaced to Lennox.
- No item ever marked done without its verification gate green.

## `/loop` — continuation, gate, stop

**CONTINUE** the loop while ALL hold:
- an unblocked build item is not yet Done, AND
- the full suite is green (the last item/milestone did not regress), AND
- no unrecoverable blocker is open, AND
- remaining work is not entirely human-gate-blocked.

**Each iteration:**
1. Pick the next unblocked item by dependency order — **foundation → bug-fix wave → features**,
   finishing the current milestone before advancing.
2. Implement (direct edits in the main agent; `Workflow` fan-out only for genuinely independent
   batches, e.g. the v0.5 test-writing sweep).
3. **VERIFY GATE (hard):** targeted tests pass **AND** full suite stays green (test count never
   decreases) **AND** render/e2e items also pass the synthetic-fixture e2e.
4. Commit on the milestone branch; update this ledger; flip Linear EDD if reachable.
5. On milestone `exit_criteria` met + a `code-reviewer` adversarial pass: ff-merge to `master`,
   tag, `pipx` reinstall global `eddy`, write a milestone report + **Second Brain log**.

**STOP / pause** when ANY:
- All milestones complete → present the human-gate batch; declare **GA-ready-pending-gate**.
- A verification gate fails and isn't green after **2 self-fix attempts** → stop, write a diagnosis,
  escalate.
- Remaining work is human-gate-blocked (money / credentials / signing / publish / non-Mac hardware)
  → stop, present the batch.
- A change would touch a forbidden surface → stop, ask.

**PACING:** self-paced via `ScheduleWakeup` between batches; no fixed clock.

**INVARIANTS (every iteration):** never mark done on assertion alone · never push · never publish ·
never touch `vendor/yt_tools/` · never mutate source video · **no real-API spend before the gate**
(local qwen + cached transcript only during the march).

## Milestone ledger

| Milestone | Branch | Status |
|-----------|--------|--------|
| v0.4 stabilize | `v0.4-stabilize` | **in progress** |
| v0.5 robustness | `v0.5-robustness` | pending |
| v0.6 crossplatform | `v0.6-crossplatform` | pending |
| v0.7 operability | `v0.7-operability` | pending |
| v0.8 breadth | `v0.8-breadth` | pending |
| v1.0 GA | `v1.0-ga` | pending |

### v0.4 items
- [x] **Model boundary** — reject non-finite timestamps at JSON/schema/compiler (`1283f5a`, +13 tests)
- [x] **Atomic state/EDL writes + tolerant loaders** — `atomicio.py`, RunState/receipts tolerant (+6 tests)
- [x] **`validate_against` recursive** (nested required + types + enums) (`base.py`, +8 tests)
- [x] **Judge clamp to 1–10 + `.get()` defect keys + in-try processing** (`judge.py`, +7 tests)
- [x] **Path-containment gate `is_relative_to` over all outputs** (excl. `-i` inputs) (`ffmpeg.py`, +6 tests)
- [x] **Slug re-hash (wrong-footage guard) + wire `--resume`** (`runs.py`, +5 tests)
- [x] **Apostrophe concat — shared `concat_quote` helper** (`ffmpeg.py`; segments+shorts) (+ tests above)
- [ ] SIGINT child-kill + idempotent post-loop resume
- [ ] Model-call + wall-clock budget
- [ ] Git-derived version + correct receipt stamp
- [ ] Privacy honesty: `--local-only`/`EDDY_OFFLINE` + consent + `local_files_only` + disclosure
- [ ] CI workflow (lint+type+test)
- [ ] Pin/record editorial model per run
- [ ] Legal drafts (LICENSE/EULA/AUP/NOTICE) → human-gate

## Human-gate batch (accumulating)
1. Legal sign-off — commercial EULA + AUP + third-party NOTICE; ffmpeg LGPL build + qwen/Whisper commercial-use rights.
2. Code-signing certs — Apple Developer ID + Windows Authenticode.
3. Private GitHub remote — for the 3-OS CI matrix + wheel smoke test.
4. Publish authorization — channel choice + public release.
5. Real-footage dogfood + capped real-API spend.
6. Any new external account/spend.

## Log
- v0.4 model-boundary fix committed `1283f5a`; suite 100 → 113 green.
- v0.4 atomic+tolerant run-state IO; suite 113 → 119 green.
- v0.4 judge hardening (clamp 1–10, .get defects, in-try processing); suite 119 → 126 green.
- v0.4 validate_against recursive (nested required/types/enums); suite 126 → 134 green.
- v0.4 apostrophe concat (shared concat_quote) + path gate (is_relative_to, all outputs); suite 134 → 142 green.
- v0.4 slug wrong-footage guard (re-hash on reopen) + --resume wired; suite 142 → 147 green.
