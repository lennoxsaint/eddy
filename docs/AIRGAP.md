# Air-gapped / offline install

Eddy is local-first: with `--local-only` (or `EDDY_OFFLINE=1`) nothing leaves the machine. Eddy's
own process is **enforced** to stay on-device — any outbound non-loopback TCP connection raises
`EgressBlocked` (see `src/eddy/netguard.py`), and offline mode refuses to select a cloud/CLI brain
that would run off-device. (The guard is in-process; it does not sandbox unrelated child processes —
see `docs/KNOWN-LIMITS.md`.) This guide installs and runs Eddy on a machine with no internet.

Three things must be staged from a connected machine, because none of them are fetched at runtime in
offline mode:

1. **The Python package + its dependency closure** — via an offline *wheelhouse*.
2. **ffmpeg** — a system binary, not a pip package.
3. **Model weights** — the Whisper transcription model and the local editorial model (qwen via Ollama).

---

## 1. Build the wheelhouse (connected machine)

> Build on the **same OS, Python minor version (3.11/3.12), and CPU architecture** as the target —
> Python wheels are platform-specific.

```bash
scripts/build_wheelhouse.sh            # writes ./wheelhouse
```

This downloads Eddy + every pinned dependency (from `requirements.lock`) as wheels. Verify the
closure is self-contained **without touching the network**:

```bash
python3 -m pip install --no-index --find-links ./wheelhouse eddy --dry-run
```

Copy the whole `wheelhouse/` folder to the air-gapped machine (USB, internal artifact store, etc).

## 2. Install on the air-gapped machine

```bash
python3 -m venv ~/.eddy-venv
~/.eddy-venv/bin/pip install --no-index --find-links /path/to/wheelhouse eddy
~/.eddy-venv/bin/eddy --version
```

`--no-index` guarantees pip never reaches PyPI; if a wheel is missing it fails loudly rather than
silently going online.

## 3. Stage ffmpeg

Eddy shells out to `ffmpeg`/`ffprobe`. Install it from your OS offline package source, or copy a
static build onto `PATH`:

- macOS: a static `ffmpeg` binary in `/usr/local/bin` (or `brew` from a local mirror).
- Linux: your distro's offline `.deb`/`.rpm`, or a static build on `PATH`.
- Windows: an `ffmpeg.exe` static build on `PATH`.

Confirm: `eddy doctor` reports ffmpeg + an available encoder.

## 4. Stage model weights

**Transcription (Whisper).** In offline mode Eddy passes `local_files_only=True`, so the
faster-whisper model must already be in the HuggingFace cache. On a connected machine, run any
transcription once (or pre-fetch the model) so it lands in `~/.cache/huggingface`, then copy that
cache to the same path on the air-gapped machine.

**Editorial brain (local).** The default offline brain is a local **qwen** model served by
[Ollama](https://ollama.com). Install Ollama offline, then stage the model blob:

```bash
# connected machine:
ollama pull qwen36-27b-codex:q4
# copy ~/.ollama/models to the air-gapped machine's ~/.ollama/models
```

Ollama serves on `127.0.0.1:11434` — loopback, so the egress guard allows it.

## 5. Run fully offline

```bash
eddy run /path/to/footage --local-only
```

You'll see `--local-only: egress guard active — outbound connections are blocked.` If anything
tries to reach the network, the run fails with `EgressBlocked` naming the host — that's the promise
being kept, not a bug. Drop `--local-only` only on a connected machine where cloud egress is
acceptable.

### What is NOT available offline
- Cloud editorial brain (Claude/OpenAI) — offline forces the local qwen model.
- Cloud thumbnail generation (Gemini/OpenAI image APIs) — skipped; provide your own thumbnail.
- Whisper model **downloads** — must be pre-staged (step 4).
