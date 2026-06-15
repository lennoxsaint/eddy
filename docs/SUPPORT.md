# Support runbook

How to triage an Eddy problem — yours or a stranger's — without their footage.

## First moves (every issue)

1. **Version + environment**: `eddy --version`, then `eddy doctor` — reports ffmpeg, an available
   encoder, free disk, hardware tier, and the resolved editorial brain.
2. **Reproduce the gate, not the render**: `eddy run <source> --dry-run` checks the environment and
   that the footage decodes, without transcribing or rendering. Most "it failed" reports are an
   ingest/environment problem this surfaces in seconds.
3. **Get the redacted diagnostic bundle**: `eddy bundle <run-dir>` writes a zip with the receipts,
   crash log, and environment fingerprint — transcript text redacted and absolute paths scrubbed.
   This is safe to share and is enough to triage most failures. No footage, transcript, or face
   frames are included.

## Common failures → cause → fix

| Symptom | Likely cause | Fix |
|---|---|---|
| `not a video/audio file` | unsupported container, or an audio file passed to `eddy run` | check `eddy doctor`; for audio use `eddy transcribe` (see audio-first ingest) |
| `… has no decodable video stream` | corrupt/truncated source, or audio-only | re-export the source; audio-only → `eddy transcribe` |
| `EgressBlocked` during a run | `--local-only`/`EDDY_OFFLINE` is set and something tried to reach the network | expected under offline mode — drop `--local-only` on a connected machine, or pre-stage models (`docs/AIRGAP.md`) |
| editorial step slow / stalls | local qwen model not pulled, or Ollama not running | `ollama list`; pull `qwen36-27b-codex:q4`; confirm Ollama on `127.0.0.1:11434` |
| no thumbnails generated | offline, or no upload consent, or no API key | expected unless `thumbnails.consent_to_upload=true` + online + key set |
| run cost-capped early | `max_run_cost_usd` reached (cloud brain) | raise the cap in config, or use `--local-only` (free) |
| captions look reversed / boxes | RTL or CJK script | use the sidecar `.srt`/`.vtt`; install Noto Sans CJK for CJK (see RTL/CJK guard) |
| crash mid-run | see the crash log path printed on failure + `eddy bundle` | attach the bundle to the report |

## Resuming and cleaning up

- **Resume** an interrupted run: `eddy run <source> --resume` (idempotent; picks up from the last
  completed phase via `state.json`).
- **Disk usage / cleanup**: `eddy clean <run-dir>` prunes scratch; `eddy clean --full` and the GDPR
  purge path remove a run (guarded so it can't delete an arbitrary path).
- **Fleet view**: `eddy runs` lists every run with its phase + best iteration.

## Escalation

If `eddy doctor` is green and `eddy bundle` doesn't reveal the cause, capture:
`eddy --version`, the `doctor` output, the bundle zip, and the exact command + first failing
receipt line. See `docs/KNOWN-LIMITS.md` before filing — the issue may be a documented limit.
