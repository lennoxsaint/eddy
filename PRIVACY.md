# Eddy — what leaves your machine

Eddy is local-first. Your **raw video and audio source files never leave your machine**, and Eddy
**never publishes or uploads anything** to YouTube, social, or anywhere. But "local-first" is not
"fully offline" by default — this page is the exact, honest per-tier data flow.

## Never sent, in any mode
- Your raw video/audio source files (they're opened read-only and sha256-verified before/after).
- Any publish/upload to YouTube, podcast hosts, or social platforms — there is no publish code.

## Default tier (`editorial = "auto"`)
The editorial brain (beat map, cut decisions, the quality judge) uses the strongest brain available
on your machine. **If** you have a `claude` or `codex` CLI installed, or an `ANTHROPIC_API_KEY` /
`OPENAI_API_KEY` set, then:
- Your **transcript text** (not the video) is sent to that cloud provider for editorial reasoning.
- Otherwise everything runs locally on your own model via Ollama.

Other steps in the default tier:
- **Transcription** (Whisper) runs locally. On first use it downloads model weights from HuggingFace.
- **Studio Sound** is Eddy's local studio-mic cleanup pass by default: FFmpeg-based denoise where
  available, mouth-click cleanup where available, speech EQ, compression/limiting, and loudness
  normalization. It operates on rendered local files and records before/after loudness proof. Exact
  Descript Studio Sound is only used when you explicitly route a Descript project workflow.
- **Thumbnails** are optional and only run if you set an image-API key (`GEMINI_API_KEY` /
  `GOOGLE_API_KEY` / `OPENAI_API_KEY`). When they run, selected **face frames** are uploaded to that
  image API. With no key, the step skips with a receipt and the kit still ships.

Every off-device call is recorded in the run's `receipts.jsonl` (look for `editorial_brain` with
`egress: true`, and `thumbnails_*`).

## Fully on-device tier (`--local-only` or `EDDY_OFFLINE=1`)
- The editorial brain is **forced to your local model** — the transcript never leaves the machine,
  even if a `claude` binary is on your PATH or an API key is set.
- Whisper uses **only already-downloaded weights** (`local_files_only`) — no HuggingFace fetch.
- The cloud thumbnail step is **skipped entirely**.

In this mode, nothing leaves your machine.

## Choosing your tier
- Want best editorial quality and have a Claude/ChatGPT subscription? Use the default — your
  transcript text goes to that provider.
- Privacy-maximalist or airgapped? Use `eddy run <footage> --local-only` (or export
  `EDDY_OFFLINE=1`).
