"""Launch kit assembler: titles, chapters, description, thumbnails, index."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.config import load_config
from eddy.edit.compiler import cut_transcript
from eddy.edit.schema import load_decisions, load_edl
from eddy.loop.receipts import Receipts
from eddy.media.frames import face_reference_frames
from eddy.package.copy import chapters, chapters_block, description, titles, write_copy_artifacts
from eddy.package.review import build_review
from eddy.package.thumbnails import generate_thumbnails
from eddy.providers.base import get_provider
from eddy.render.long import latest_iteration_dir
from eddy.transcribe.pack import phrases as load_phrases


def package_run(run_dir: Path, iteration_dir: Path | None = None) -> Path:
    run_dir = Path(run_dir).expanduser().resolve()
    cfg = load_config()
    receipts = Receipts(run_dir)
    provider = get_provider(cfg)
    iter_dir = Path(iteration_dir) if iteration_dir else latest_iteration_dir(run_dir)

    decisions = load_decisions(iter_dir / "edit-decisions.json")
    edl_path = run_dir / "final" / "edl.json"
    edl = load_edl(edl_path if edl_path.exists() else iter_dir / "edl.json")
    kept = cut_transcript(edl, load_phrases(run_dir))
    final_dir = run_dir / "final"

    # copy
    title_list = titles(kept, provider, receipts)
    chaps = chapters(edl, decisions, provider, receipts)
    desc = description(kept, chaps, provider, receipts)
    write_copy_artifacts(final_dir, title_list, desc, chaps)

    # thumbnails from sharp face frames at beat starts / high-energy moments
    final_video = final_dir / "video.mp4"
    thumb_paths: list[Path] = []
    if final_video.exists():
        moments = [c["out_s"] + 2.0 for c in chaps[:8]] or [5.0, 30.0, 60.0]
        refs = face_reference_frames(final_video, moments, final_dir / "thumbnails" / "refs", run_dir)
        hint = title_list[0]["title"] if title_list else run_dir.name
        thumb_paths = generate_thumbnails(run_dir, refs, hint, cfg, receipts)

    # transcript of the final cut
    (final_dir / "transcript.md").write_text(
        "\n".join(f"[{p['out_start']:.1f}] {p['text']}" for p in kept) + "\n"
    )
    # sidecar subtitles (.srt + .vtt) — accessibility + SEO for the long video
    from eddy.render.subtitles import write_subtitles

    subs = write_subtitles(kept, final_dir, stem="subtitles")

    # benchmark-format conversion for objective diffs
    (final_dir / "edit-decisions.benchmark.json").write_text(
        json.dumps(edl.to_benchmark_format(slug=run_dir.name), indent=2)
    )

    # kit index
    kit_dir = final_dir / "launch-kit"
    kit_dir.mkdir(exist_ok=True)
    shorts_ledger = final_dir / "shorts" / "shorts-ledger.json"
    shorts = json.loads(shorts_ledger.read_text()) if shorts_ledger.exists() else []
    qa_final = final_dir / "qa-final.json"
    qa = json.loads(qa_final.read_text()) if qa_final.exists() else {}
    # plain-language "review these moments" note for a non-engineer creator
    review = build_review(run_dir, iter_dir, edl.total_duration_s, cfg.loop.length_ceiling_minutes * 60)
    # AI-generated content disclosure (titles/description/thumbnails are model output)
    (final_dir / "AI-DISCLOSURE.md").write_text(
        "# AI-generated content disclosure\n\n"
        "These launch-kit assets are AI-generated — review before publishing:\n"
        "- **Titles** — model-written (grounded in transcript quotes)\n"
        "- **Description + chapter labels** — model-written\n"
        "- **Thumbnails** — AI image edits of your own face frame (only if you enabled upload consent)\n\n"
        "Verify accuracy and likeness, ensure no claim is misleading, and disclose AI generation "
        "where your platform requires it.\n"
    )

    index = [
        f"# Launch Kit — {run_dir.name}",
        "",
        "- **Video:** `final/video.mp4`" + (" (final QA: PASS)" if qa.get("pass") else " (final QA: CHECK qa-final.json)"),
        "- **Review notes:** `final/REVIEW.md`" + (f" ({review['flagged']} moment(s) flagged)" if review["flagged"] else " (clean)"),
        f"- **Titles:** `final/titles.md` ({len(title_list)} candidates, top: \"{title_list[0]['title'] if title_list else '—'}\")",
        "- **Description + chapters:** `final/description.md`, `final/chapters.txt`",
        f"- **Shorts:** {sum(1 for s in shorts if s.get('status') == 'rendered')} rendered in `final/shorts/`",
        f"- **Thumbnails:** {len(thumb_paths)} candidates in `final/thumbnails/`"
        + ("" if thumb_paths else " (skipped — see receipts)"),
        "- **Final transcript:** `final/transcript.md`",
        f"- **Subtitles:** `final/subtitles.srt`, `final/subtitles.vtt` ({subs['cues']} cues)",
        "- **Receipts:** `receipts.jsonl`",
        "",
        "## Chapters",
        "",
        chapters_block(chaps),
        "",
        "## Shorts",
        "",
    ]
    for s in shorts:
        if s.get("status") == "rendered":
            index.append(f"- `{s['slug']}.mp4` — {s['duration_s']}s — hook: {s.get('hook', '')!r} — QA {'PASS' if s.get('qa_pass') else 'FAIL'}")
    (kit_dir / "LAUNCH-KIT.md").write_text("\n".join(index) + "\n")

    receipts.log("launch_kit", titles=len(title_list), chapters=len(chaps), shorts=len(shorts), thumbnails=len(thumb_paths))
    print(kit_dir / "LAUNCH-KIT.md")
    return kit_dir
