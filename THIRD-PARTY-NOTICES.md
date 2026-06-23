# Third-party notices

Eddy is MIT-licensed, but it invokes third-party libraries, command-line tools, model weights, and
optional cloud services whose own licenses and terms still apply. Verify pinned dependency versions
and any bundled binary license before cutting a release artifact.

## Python dependencies (PyPI, installed alongside Eddy)
| Component | Purpose | License (typical) |
|-----------|---------|-------------------|
| typer | CLI framework | MIT |
| pydantic | schemas/config | MIT |
| tomlkit | config round-trip | MIT |
| pillow | thumbnail/caption raster | MIT-CMU (HPND) |
| openai | OpenAI API client | Apache-2.0 |
| anthropic | Anthropic API client | MIT |
| faster-whisper | transcription (CTranslate2) | MIT |
| httpx | HTTP client | BSD-3-Clause |

These are permissive (MIT/BSD/Apache/HPND) in their common published forms and compatible with MIT
distribution when their copyright/license notices are preserved. Generate a complete, pinned list
with `pip-licenses` for release packages.

## System / bundled binaries
- **FFmpeg** — invoked for all media operations. FFmpeg can be built under **LGPL-2.1+** or
  **GPL-2.0+** depending on which external libraries are compiled in (e.g. libx264 / libfdk-aac pull
  in GPL/non-free terms). For a commercial, non-copyleft distribution you must ship (or require) an
  **LGPL build of FFmpeg without GPL/non-free components**, and provide the corresponding notices
  and (for LGPL) a way to relink. Confirm the exact FFmpeg build and its license before bundling.

## Model weights (downloaded at runtime, not bundled)
- **Whisper `large-v3`** (via faster-whisper / CTranslate2) — model weights are downloaded from
  HuggingFace on first use. Confirm the weights' license permits commercial use and redistribution
  if you ever bundle them for an offline wheelhouse (v1.0 task).
- **Ollama models (e.g. qwen 27B)** — pulled by the user via Ollama; governed by each model's own
  license (e.g. the Qwen license). Eddy does not redistribute these weights. Confirm commercial-use
  terms for any model you recommend by default.

## Cloud services (optional, user-provided credentials)
- Anthropic API / Claude CLI, OpenAI API / Codex CLI — used for editorial reasoning only when the
  user has configured them; governed by the provider's terms. The user's transcript text is sent to
  the chosen provider (see PRIVACY.md).
- Image APIs (Gemini / OpenAI) — used only for the optional thumbnail step; selected face frames are
  uploaded. Confirm the provider's terms on uploaded-likeness usage.

## Vendored code
- `vendor/yt_tools/` — historical reference scripts copied from a prior internal creator-editing
  workflow. They are retained as read-only implementation references, not runtime entrypoints. Do not
  put private paths, keys, or footage-specific values in production code.
