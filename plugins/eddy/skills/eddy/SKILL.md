---
name: eddy
description: Use Eddy to turn attached raw video footage into a proof-gated YouTube long edit and Shorts.
---

# Eddy

Use this skill when the user mentions Eddy, attaches video footage, or asks for a YouTube edit.

## Default Behavior

If the user attaches raw video footage and gives no other instruction, treat the job as:

> Edit this footage into a finished YouTube long-form video and Shorts.

First ask Eddy what edit paths are available:

```text
eddy_edit_options(source=<attached file or folder path>, format="youtube")
```

If `requires_choice` is true, ask the user exactly:

> How do you want this edited?

Show the runnable options in plain English: what each option is, practical benefits, drawbacks, privacy/cost notes, and the recommended option. Do not show unavailable setup suggestions as selectable choices.

If `requires_choice` is false, do not ask. Start the edit with the selected option:

```text
eddy_edit_start(
  source=<attached file or folder path>,
  format="youtube",
  edit_path=<selected_option_id>,
  auto_fallback=true,
  fallback_policy="agent_subscription"
)
```

If Codex cannot resolve the attachment into a filesystem path, stop with the exact blocker
`attached_source_unresolved` and ask the user to paste the local file path or attach a folder that
Codex exposes as a path. Do not guess.

## Bootstrap

The plugin MCP wrapper automatically keeps Eddy on the latest stable GitHub tag. On install and on
first use, it:

1. checks the latest stable `vX.Y.Z` tag from `https://github.com/lennoxsaint/eddy`;
2. installs that tag into `~/.eddy/source` and `~/.eddy/venv`;
3. smoke-checks the installed engine before switching versions;
4. keeps the previous working version if the update fails;
5. writes receipts to `~/.eddy/plugin-state.json`.

After bootstrap, the wrapper launches Eddy's MCP server from the active managed venv. If a newer tag
fails to install, report the exact blocker and continue only if a previous working tag is available.

## Editing Rules

- Never mutate, move, delete, upload, publish, send, or schedule source media.
- "Perfectly edited" means proof-gated: every required Eddy gate passed. If gates are red, report exact
  blockers and evidence instead of calling the output perfect.
- Long-form output should include the edited video, transcript, QA receipts, and launch-kit assets
  when the run reaches those gates.
- Shorts are quality-gated. If separate camera and screen sources exist, Eddy uses the Yassy stacked
  layout: square camera top, one-line karaoke captions in the middle, screen/proof panel bottom.
- If only one talking-head video source exists and no screen source is discovered, Eddy uses the
  `talking_head_916` Shorts layout: crop/fill the talking head to 1080x1920, keep the face centered,
  preserve blinkless segment assembly, and place one-line karaoke captions in the bottom third.
- If an audio-only source or ambiguous multi-file source is supplied, fail loudly with the exact
  blocker instead of rendering a weak output.
- Studio Sound is a hard gate for final edits. Do not silently downgrade to basic EQ/loudness.
- Premium motion graphics require a project-local `frame.md`, `storyboard.md`, static
  `storyboard.html`, copied HyperFrames references, and collision proof before compositing.

## Fallback

If the selected edit path stalls, errors, or repeats the same gate failure without improvement, Eddy
should automatically fall back to the best allowed alternative path, usually the current host
assistant/subscription route. Do not silently fall back to metered OpenAI or Anthropic API usage unless
the run has an explicit cost cap.

For a host-agent edit path, wait for the job to reach `awaiting_host_decisions`, call:

```text
eddy_host_packet(job_id=<job_id>)
```

Use that packet to produce a valid `EditDecisions` JSON payload, then submit it:

```text
eddy_host_submit(job_id=<job_id>, payload=<EditDecisions JSON>)
```

Invalid host payloads are blockers to repair, not crashes. The packet contains transcript/QA text and
source hashes, never media bytes.

If plugin MCP tools are not visible yet, use the repo fallback from a cloned checkout:

```bash
python3 scripts/install_codex.py
eddy edit /path/to/footage-or-folder
```

Return local output paths and blockers only. Eddy does not perform public publishing actions.
