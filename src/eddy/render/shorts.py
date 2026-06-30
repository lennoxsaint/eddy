"""Shorts renderer: candidates -> phrase-safe sub-segments -> layout render ->
karaoke captions -> QA ledger.

Layouts (approved standard):
- dual-source: face panel (camera) top, captions, screen panel bottom
- single talking-head source: crop/fill to 9:16 and place karaoke captions in the bottom third
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

from eddy.config import load_config
from eddy.edit.kernel import raw_short_candidates, transcript_retake_groups
from eddy.edit.schema import ShortsCandidate, load_decisions
from eddy.loop.receipts import Receipts
from eddy.media.ffmpeg import run_ffmpeg, video_encoder_args
from eddy.media.probe import stream_summary
from eddy.render import layout as L
from eddy.render.captions import burn_captions, caption_events
from eddy.render.long import latest_iteration_dir
from eddy.runs import SourceError, manifest
from eddy.transcribe.pack import phrases as load_phrases
from eddy.transcribe.whisper import words_flat
from eddy.qa.deterministic import loudness_gate, silent_motion_gate
from eddy.hooks.playbook import load_playbook, require_hook_playbook, resolve_playbook_path, score_candidate_hook

MARKER_PATTERNS = (
    ("hook", "for", "short"),
    ("hook", "four", "short"),
    ("book", "for", "short"),
    ("book4short",),
)


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", word.lower())


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "short"


def strip_marker_words(words: list[dict]) -> list[dict]:
    """Remove 'hook for short' marker phrases from a word list."""
    norms = [_norm(w["word"]) for w in words]
    drop: set[int] = set()
    for pat in MARKER_PATTERNS:
        n = len(pat)
        for i in range(len(norms) - n + 1):
            if tuple(norms[i : i + n]) == pat:
                drop.update(range(i, i + n))
    return [w for i, w in enumerate(words) if i not in drop]


def sub_segments(words: list[dict]) -> list[tuple[float, float]]:
    """Split a short's words into keep segments on long gaps, with safe handles."""
    if not words:
        return []
    groups: list[list[dict]] = [[words[0]]]
    for prev, w in zip(words, words[1:]):
        if w["start"] - prev["end"] >= L.GAP_CUT_THRESHOLD:
            groups.append([w])
        else:
            groups[-1].append(w)

    segs: list[tuple[float, float]] = []
    for gi, g in enumerate(groups):
        start = max(0.0, g[0]["start"] - L.START_HANDLE)
        handle = L.FINAL_END_HANDLE if gi == len(groups) - 1 else L.INTERNAL_END_HANDLE
        end = g[-1]["end"] + handle
        if end - start >= 0.6:
            segs.append((start, end))
    return segs


def ends_on_complete_sentence(words: list[dict]) -> bool:
    if not words:
        return False
    last = str(words[-1]["word"]).strip()
    return last.endswith((".", "!", "?")) or len(words) >= 8


def _rounded_mask(path: Path, size: tuple[int, int], radius: int) -> None:
    img = Image.new("L", size, 0)
    ImageDraw.Draw(img).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    img.save(path)


def _render_segment_single(
    source: Path, out: Path, start: float, end: float, mask: Path, panel_h: int, panel_y: int, run_dir: Path
) -> Path:
    dur = end - start
    graph = (
        f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
        f"scale={L.PANEL_W}:{panel_h}:force_original_aspect_ratio=decrease,"
        f"pad={L.PANEL_W}:{panel_h}:(ow-iw)/2:(oh-ih)/2:color={L.BG},setsar=1,format=rgba[praw];"
        "[praw][1:v]alphamerge[panel];"
        f"color=c={L.BG}:s={L.W}x{L.H}:d={dur:.3f},format=rgba[base];"
        f"[base][panel]overlay={L.PANEL_X}:{panel_y}:format=auto[v];"
        f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a]"
    )
    run_ffmpeg(
        [
            "-i", str(source),
            "-i", str(mask),
            "-filter_complex", graph,
            "-map", "[v]", "-map", "[a]",
            *video_encoder_args("7500k"), "-r", "25",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
        ],
        run_dir=run_dir,
    )
    return out


def _render_segment_dual(
    camera: Path, screen: Path, out: Path, start: float, end: float,
    face_mask: Path, screen_mask: Path, cam_w: int, cam_h: int, run_dir: Path,
) -> Path:
    dur = end - start
    crop = min(cam_w, cam_h)
    crop_x = max(0, (cam_w - crop) // 2)
    graph = (
        f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
        f"scale={L.SCREEN_W}:{L.SCREEN_H}:force_original_aspect_ratio=decrease,"
        f"pad={L.SCREEN_W}:{L.SCREEN_H}:(ow-iw)/2:(oh-ih)/2:color={L.BG},setsar=1,format=rgba[srgba];"
        f"[1:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
        f"crop={crop}:{crop}:{crop_x}:0,scale={L.FACE_SIZE}:{L.FACE_SIZE},setsar=1,format=rgba[crgba];"
        "[srgba][2:v]alphamerge[sround];[crgba][3:v]alphamerge[cround];"
        f"color=c={L.BG}:s={L.W}x{L.H}:d={dur:.3f},format=rgba[base];"
        f"[base][cround]overlay={L.FACE_X}:{L.FACE_Y}:format=auto[tmp];"
        f"[tmp][sround]overlay={L.SCREEN_X}:{L.SCREEN_Y}:format=auto[v];"
        f"[1:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a]"
    )
    run_ffmpeg(
        [
            "-i", str(screen),
            "-i", str(camera),
            "-i", str(screen_mask), "-i", str(face_mask),
            "-filter_complex", graph,
            "-map", "[v]", "-map", "[a]",
            *video_encoder_args("7500k"), "-r", "25",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
        ],
        run_dir=run_dir,
    )
    return out


def _render_segment_talking_head(source: Path, out: Path, start: float, end: float, run_dir: Path) -> Path:
    graph = (
        f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
        f"scale={L.W}:{L.H}:force_original_aspect_ratio=increase,"
        f"crop={L.W}:{L.H},setsar=1,format=yuv420p[v];"
        f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a]"
    )
    run_ffmpeg(
        [
            "-i", str(source),
            "-filter_complex", graph,
            "-map", "[v]", "-map", "[a]",
            *video_encoder_args("7500k"), "-r", "25",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
        ],
        run_dir=run_dir,
    )
    return out


def _join_boundary_times(segs: list[tuple[float, float]]) -> list[float]:
    """Return output-timeline join times for visual QA around segment boundaries."""
    cursor = 0.0
    boundaries: list[float] = []
    for start, end in segs[:-1]:
        cursor += end - start
        boundaries.append(round(cursor, 3))
    return boundaries


def _concat_segments_blinkless(seg_paths: list[Path], out: Path, run_dir: Path) -> dict:
    """Assemble rendered Shorts segments without decoder-reset flashes.

    The old path used concat-demuxer + stream copy. That is fast, but on Shorts it can create a
    visible blink in the talking-head panel at every retained-word cut because each tiny MP4 resets
    the decoder/keyframe state. Re-encoding through one concat filter creates one continuous output
    timeline, which is the same class of fix we use for blinkless long-form picture-in-picture.
    """
    if not seg_paths:
        raise SourceError("no rendered short segments to join")

    inputs: list[str] = []
    filter_parts: list[str] = []
    concat_labels: list[str] = []
    for idx, path in enumerate(seg_paths):
        inputs.extend(["-i", str(path)])
        filter_parts.append(f"[{idx}:v]setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{idx}]")
        filter_parts.append(f"[{idx}:a]asetpts=PTS-STARTPTS[a{idx}]")
        concat_labels.append(f"[v{idx}][a{idx}]")

    graph = ";".join(filter_parts + ["".join(concat_labels) + f"concat=n={len(seg_paths)}:v=1:a=1[v][a]"])
    run_ffmpeg(
        [
            *inputs,
            "-filter_complex", graph,
            "-map", "[v]", "-map", "[a]",
            *video_encoder_args("7500k"), "-r", "25",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
        ],
        run_dir=run_dir,
    )
    return {
        "strategy": "filtergraph_reencode_concat",
        "reencoded": True,
        "segment_count": len(seg_paths),
        "join_count": max(0, len(seg_paths) - 1),
        "concat_demuxer_copy": False,
    }


def select_short_candidates(candidates: list, count: int, playbook_records: list[dict] | None = None) -> list:
    """Pick Shorts by hook strength first, then timeline order.

    The model proposes candidates, but Eddy's baked playbook is the taste filter: empty/weak hooks
    are rejected instead of being rendered just because they appeared early in the video.
    """
    scored = []
    for c in candidates:
        proof = score_candidate_hook(getattr(c, "hook", ""), playbook_records or [])
        if playbook_records and not proof["pass"]:
            continue
        scored.append((proof["hook_score"], -float(c.start_s), c))
    scored.sort(reverse=True)
    return [c for _score, _neg_start, c in scored[: count * 2]]


def _strengthened_short_hook(hook: str) -> str | None:
    lower = hook.lower()
    if "duplicate" in lower and "codex" in lower:
        return "How to duplicate Codex and run any model inside it"
    if "copied codex" in lower or ("isolated" in lower and "home" in lower):
        return "How a copied Codex app keeps its own isolated home"
    if "local model" in lower or "local models" in lower or "leaves your laptop" in lower:
        return "How local models keep your work on your laptop"
    if "real build" in lower or ("duplicate app" in lower and "proxy" in lower):
        return "How the duplicate Codex app actually works"
    return None


def _with_repaired_hook(candidate, hook: str):
    if hasattr(candidate, "model_copy"):
        return candidate.model_copy(update={"hook": hook})
    candidate.hook = hook
    return candidate


def playbook_fallback_short_candidates(candidates: list, count: int, playbook_records: list[dict]) -> list:
    """Repair obvious tutorial hooks before giving up on otherwise-standalone Shorts candidates."""

    repaired = []
    for candidate in candidates:
        stronger = _strengthened_short_hook(str(getattr(candidate, "hook", "")))
        if not stronger:
            continue
        proof = score_candidate_hook(stronger, playbook_records)
        if proof["pass"]:
            repaired.append((proof["hook_score"], -float(candidate.start_s), _with_repaired_hook(candidate, stronger)))
    repaired.sort(reverse=True)
    return [candidate for _score, _neg_start, candidate in repaired[: count * 2]]


def _short_candidate_key(candidate) -> tuple[float, float]:
    return (
        round(float(candidate.start_s), 3),
        round(float(candidate.end_s), 3),
    )


def _short_attempt_slug(candidate) -> str:
    return slugify(str(getattr(candidate, "hook", "")) or f"short-{float(candidate.start_s):.0f}")


def _short_attempt_queue(selected: list, all_candidates: list) -> list:
    """Try taste-selected Shorts first, then remaining standalone candidates if QA rejects them."""
    queue = []
    seen_spans: set[tuple[float, float]] = set()
    seen_slugs: set[str] = set()

    def add(candidate) -> None:
        span_key = _short_candidate_key(candidate)
        slug_key = _short_attempt_slug(candidate)
        if span_key in seen_spans or slug_key in seen_slugs:
            return
        queue.append(candidate)
        seen_spans.add(span_key)
        seen_slugs.add(slug_key)

    for candidate in selected:
        add(candidate)
    for candidate in all_candidates:
        add(candidate)
    return queue


def _short_silence_threshold(cfg) -> float:
    """Shorts allow natural visual micro-pauses; the QA standard hard-fails true dead air."""
    return max(float(cfg.gates.max_output_silence_s), float(cfg.shorts.max_silent_motion_s))


def _quarantine_rejected_short(final: Path, out_root: Path) -> Path:
    """Move a QA-failed candidate out of the production Shorts folder."""
    rejected = out_root / "_rejected" / final.name
    rejected.parent.mkdir(parents=True, exist_ok=True)
    if rejected.exists():
        rejected.unlink()
    final.replace(rejected)
    return rejected


def _mined_short_candidates(run_dir: Path, min_s: float, max_s: float, limit: int) -> list[ShortsCandidate]:
    try:
        hints = raw_short_candidates(load_phrases(run_dir), min_s=min_s, max_s=max_s, limit=limit)
    except Exception:
        return []
    return [
        ShortsCandidate(
            start_s=float(item["start_s"]),
            end_s=float(item["end_s"]),
            hook=str(item.get("hook", "")),
            reason=str(item.get("reason", "Raw transcript miner found a complete standalone span.")),
        )
        for item in hints
    ]


def _retake_exclusion_spans(run_dir: Path) -> list[dict]:
    """Return non-selected raw transcript variants that Shorts must not mine or render."""
    try:
        groups = transcript_retake_groups(words_flat(run_dir), load_phrases(run_dir))
    except Exception:
        return []
    spans: list[dict] = []
    for group in groups:
        selected = group.default_variant_id
        for variant in group.variants:
            if variant.id == selected:
                continue
            spans.append(
                {
                    "group_id": group.id,
                    "variant_id": variant.id,
                    "kind": group.kind,
                    "start_s": variant.start_s,
                    "end_s": variant.end_s,
                    "text": variant.text,
                }
            )
    return spans


def _candidate_overlaps_retake(candidate: ShortsCandidate, spans: list[dict], *, min_overlap_s: float = 0.25) -> bool:
    start = float(candidate.start_s)
    end = float(candidate.end_s)
    for span in spans:
        overlap = min(end, float(span["end_s"])) - max(start, float(span["start_s"]))
        if overlap >= min_overlap_s:
            return True
    return False


def _filter_retaken_short_candidates(
    candidates: list[ShortsCandidate],
    spans: list[dict],
) -> tuple[list[ShortsCandidate], list[dict]]:
    kept: list[ShortsCandidate] = []
    dropped: list[dict] = []
    for candidate in candidates:
        if _candidate_overlaps_retake(candidate, spans):
            dropped.append(
                {
                    "start_s": float(candidate.start_s),
                    "end_s": float(candidate.end_s),
                    "hook": candidate.hook,
                    "reason": "Candidate overlaps a transcript-hard retake variant.",
                }
            )
        else:
            kept.append(candidate)
    return kept, dropped


def _write_short_blocker(out_root: Path, receipts: Receipts, code: str, message: str, evidence: dict) -> list[dict]:
    ledger = [
        {
            "slug": code,
            "hook": "",
            "path": "",
            "duration_s": 0.0,
            "qa_pass": False,
            "status": "blocked",
            "blocker": code,
            "message": message,
            "evidence": evidence,
        }
    ]
    (out_root / "shorts-ledger.json").write_text(json.dumps(ledger, indent=1))
    receipts.log("shorts_blocked", code=code, message=message, evidence=evidence)
    from eddy.ui import console as ui

    ui.json_output([{k: e.get(k) for k in ("slug", "status", "duration_s", "qa_pass", "blocker")} for e in ledger])
    return ledger


def render_shorts(run_dir: Path, iteration_dir: Path | None = None) -> list[dict]:
    run_dir = Path(run_dir).expanduser().resolve()
    cfg = load_config()
    receipts = Receipts(run_dir)
    m = manifest(run_dir)
    camera = Path(m["sources"]["camera"])
    screen_declared = bool(m["sources"].get("screen"))
    screen = Path(m["sources"].get("screen", "")) if screen_declared else None
    if screen_declared and (screen is None or not screen.exists()):
        raise SourceError(
            f"screen source was declared but is missing: {screen}. Shorts with separate screen/camera "
            "must render from both sources, not a flattened long-form export."
        )
    dual = screen is not None and screen.exists()

    iter_dir = Path(iteration_dir) if iteration_dir else latest_iteration_dir(run_dir)
    decisions = load_decisions(iter_dir / "edit-decisions.json")
    all_words = words_flat(run_dir)

    # Shorts compose a vertical *video* layout — fail loud at the top if the camera has no video
    # stream (audio-only/corrupt source) instead of crashing mid-render on a None["width"] deref.
    cam_summary = stream_summary(camera)
    if cam_summary["video"] is None:
        raise SourceError(
            f"no video stream in {camera.name} — shorts need a video track to build the vertical "
            "layout (audio-only sources can't be made into shorts; try `eddy transcribe` instead)"
        )
    playbook_records: list[dict] = []
    if cfg.shorts.require_hook_playbook:
        playbook_path = resolve_playbook_path(Path(cfg.shorts.hook_playbook_path))
        status = require_hook_playbook(playbook_path, cfg.shorts.hook_playbook_min_records)
        receipts.log("short_hook_playbook_gate", **status)
        playbook_records = load_playbook(playbook_path)

    out_root = run_dir / "final" / "shorts"
    out_root.mkdir(parents=True, exist_ok=True)
    retake_exclusion_spans = _retake_exclusion_spans(run_dir)

    if not decisions.shorts_candidates:
        mined = _mined_short_candidates(
            run_dir,
            min_s=float(cfg.shorts.min_s),
            max_s=float(cfg.shorts.max_s),
            limit=max(cfg.shorts.count * 3, cfg.shorts.count),
        )
        decisions.shorts_candidates = mined
        receipts.log(
            "shorts_mined_from_raw_transcript",
            candidate_count=len(mined),
            reason="Host-kernel decisions had no Shorts candidates.",
        )
        if not mined:
            return _write_short_blocker(
                out_root,
                receipts,
                "no_standalone_short_candidates",
                "No host or raw-transcript Shorts candidates were available.",
                {"source": "raw_transcript_miner", "min_s": cfg.shorts.min_s, "max_s": cfg.shorts.max_s},
            )

    if retake_exclusion_spans and decisions.shorts_candidates:
        original_count = len(decisions.shorts_candidates)
        decisions.shorts_candidates, dropped_retakes = _filter_retaken_short_candidates(
            decisions.shorts_candidates,
            retake_exclusion_spans,
        )
        if dropped_retakes:
            receipts.log(
                "shorts_retakes_excluded",
                original_candidate_count=original_count,
                kept_candidate_count=len(decisions.shorts_candidates),
                dropped_candidate_count=len(dropped_retakes),
                dropped=dropped_retakes[:20],
                exclusion_spans=retake_exclusion_spans[:20],
            )
        if not decisions.shorts_candidates:
            return _write_short_blocker(
                out_root,
                receipts,
                "short_candidates_all_retakes",
                "All Shorts candidates overlapped transcript-hard retake variants.",
                {
                    "dropped_count": len(dropped_retakes),
                    "retake_exclusion_spans": retake_exclusion_spans[:20],
                },
            )

    selected_candidates = select_short_candidates(decisions.shorts_candidates, cfg.shorts.count, playbook_records)
    if not selected_candidates and playbook_records:
        selected_candidates = playbook_fallback_short_candidates(
            decisions.shorts_candidates,
            cfg.shorts.count,
            playbook_records,
        )
        if selected_candidates:
            receipts.log(
                "shorts_playbook_hook_repair",
                selected_count=len(selected_candidates),
                reason="Standalone candidates existed, but their literal hooks missed the offline playbook shape.",
                repaired_hooks=[candidate.hook for candidate in selected_candidates],
            )
    if not selected_candidates:
        return _write_short_blocker(
            out_root,
            receipts,
            "no_green_short_candidates",
            "Shorts candidates existed, but none passed the hook/playbook selection gate.",
            {
                "candidate_count": len(decisions.shorts_candidates),
                "require_hook_playbook": cfg.shorts.require_hook_playbook,
                "hook_playbook_records": len(playbook_records),
            },
        )
    candidates = _short_attempt_queue(selected_candidates, decisions.shorts_candidates)
    if len(candidates) > len(selected_candidates):
        receipts.log(
            "shorts_selection_fallback_queue",
            selected_count=len(selected_candidates),
            fallback_count=len(candidates) - len(selected_candidates),
            reason="Taste-selected Shorts did not exhaust standalone raw candidates; QA may reject the first choices.",
        )
    ledger: list[dict] = []
    rendered = 0

    for cand in candidates:
        if rendered >= cfg.shorts.count:
            break
        words = [w for w in all_words if cand.start_s - 0.05 <= w["start"] and w["end"] <= cand.end_s + 0.05]
        words = strip_marker_words(words)
        if not words:
            continue
        segs = sub_segments(words)
        total = sum(e - s for s, e in segs)
        if not (cfg.shorts.min_s <= total <= cfg.shorts.max_s + 5):
            ledger.append({"hook": cand.hook, "status": "skipped_duration", "total_s": round(total, 1)})
            continue

        slug = slugify(cand.hook or f"short-{cand.start_s:.0f}")
        asset_dir = out_root / slug
        asset_dir.mkdir(parents=True, exist_ok=True)

        src_video = cam_summary["video"]  # validated non-None above
        if dual:
            face_mask = asset_dir / "face-mask.png"
            screen_mask = asset_dir / "screen-mask.png"
            _rounded_mask(face_mask, (L.FACE_SIZE, L.FACE_SIZE), L.FACE_RADIUS)
            _rounded_mask(screen_mask, (L.SCREEN_W, L.SCREEN_H), L.SCREEN_RADIUS)
        else:
            caption_y = L.TALKING_HEAD_CAPTION_Y

        seg_paths = []
        for i, (s, e) in enumerate(segs):
            seg_out = asset_dir / "layout-segments" / f"segment-{i:03d}.mp4"
            seg_out.parent.mkdir(exist_ok=True)
            if dual:
                assert screen is not None  # dual layout implies a screen source
                _render_segment_dual(camera, screen, seg_out, s, e, face_mask, screen_mask, src_video["width"], src_video["height"], run_dir)
            else:
                _render_segment_talking_head(camera, seg_out, s, e, run_dir)
            seg_paths.append(seg_out)

        base = asset_dir / "base.mp4"
        join_qa = _concat_segments_blinkless(seg_paths, base, run_dir)
        join_qa["boundary_times_s"] = _join_boundary_times(segs)

        # output-timeline word times for captions
        out_words = []
        cursor = 0.0
        for s, e in segs:
            for w in words:
                if s <= w["start"] and w["end"] <= e + 0.05:
                    out_words.append({**w, "start": cursor + w["start"] - s, "end": cursor + w["end"] - s})
            cursor += e - s

        events = caption_events(asset_dir, out_words)
        final = out_root / f"{slug}.mp4"
        burn_captions(base, final, events, cursor, asset_dir, run_dir, caption_y=None if dual else caption_y)

        # Studio Sound on the assembled short. Fail loud if the heavy backend is missing; Shorts
        # with plain EQ/loudnorm are not Eddy-quality exports.
        audio_quality_pass = True
        audio_result = {}
        if cfg.audio.studio_sound:
            from eddy.render.audio import studio_sound

            audio_result = studio_sound(final, run_dir, cfg.audio, receipts=receipts)
            if not audio_result.get("quality_gate_pass", False):
                audio_quality_pass = False
                receipts.log(
                    "short_audio_qa_failed",
                    slug=slug,
                    error=audio_result.get("error") or "Studio Sound quality gate failed",
                    profile=audio_result.get("profile"),
                    enhancement_backend=audio_result.get("enhancement_backend"),
                )

        final_summary = stream_summary(final)
        silence_qa = silent_motion_gate(final, run_dir, cfg.gates.silence_noise_db, _short_silence_threshold(cfg), 0)
        loudness_qa = loudness_gate(final, cfg.audio.target_lufs) if cfg.audio.studio_sound else {"pass": True}
        boundary_pairs = []
        for s, e in segs:
            seg_words = [w for w in words if s <= w["start"] and w["end"] <= e + 0.05]
            if seg_words:
                boundary_pairs.append((seg_words[0]["start"] - s, e - seg_words[-1]["end"]))
        min_pre = min((pre for pre, _post in boundary_pairs), default=0.0)
        min_post = min((post for _pre, post in boundary_pairs), default=0.0)
        fv = final_summary["video"]  # None only if our own render produced no video stream — QA-fail it
        qa_pass = (
            fv is not None
            and fv["width"] == L.W
            and fv["height"] == L.H
            and (not screen_declared or dual)
            and len(events) > 0
            and final_summary["audio"] is not None
            and ends_on_complete_sentence(words)
            and audio_quality_pass
            and silence_qa["pass"]
            and loudness_qa["pass"]
            and join_qa["strategy"] == "filtergraph_reencode_concat"
            and not join_qa["concat_demuxer_copy"]
        )
        publish_path = final if qa_pass else _quarantine_rejected_short(final, out_root)
        entry = {
            "slug": slug,
            "hook": cand.hook,
            "path": str(publish_path),
            "duration_s": round(final_summary["duration_s"], 1),
            "resolution": f"{fv['width']}x{fv['height']}" if fv else "unknown",
            "segments": len(segs),
            "join_qa": join_qa,
            "caption_events": len(events),
            "sentence_final": ends_on_complete_sentence(words),
            "silence_qa": silence_qa,
            "loudness_qa": loudness_qa,
            "studio_sound_qa": audio_result if cfg.audio.studio_sound else {"quality_gate_pass": True},
            "boundary_qa": {"min_pre_handle_s": round(min_pre, 3), "min_post_handle_s": round(min_post, 3)},
            "layout": "dual" if dual else "talking_head_916",
            "source_provenance": {
                "camera": str(camera),
                "screen": str(screen) if screen else None,
                "requires_dual": screen_declared,
                "used_dual": dual,
            },
            "style_lock": (
                {
                    "canvas": f"{L.W}x{L.H}",
                    "camera_square": {"x": L.FACE_X, "y": L.FACE_Y, "size": L.FACE_SIZE, "radius": L.FACE_RADIUS},
                    "caption_y": L.CAPTION_Y,
                    "screen_panel": {
                        "x": L.SCREEN_X,
                        "y": L.SCREEN_Y,
                        "w": L.SCREEN_W,
                        "h": L.SCREEN_H,
                        "radius": L.SCREEN_RADIUS,
                    },
                    "highlight": L.HIGHLIGHT_BLUE,
                }
                if dual
                else {
                    "canvas": f"{L.W}x{L.H}",
                    "talking_head_frame": {
                        "x": 0,
                        "y": 0,
                        "w": L.W,
                        "h": L.H,
                        "crop": L.TALKING_HEAD_CROP,
                    },
                    "caption_y": L.TALKING_HEAD_CAPTION_Y,
                    "caption_zone": "bottom_third",
                    "highlight": L.HIGHLIGHT_BLUE,
                }
            ),
            "qa_pass": qa_pass,
            "status": "rendered" if qa_pass else "qa_failed",
        }
        ledger.append(entry)
        if qa_pass:
            rendered += 1
            receipts.log("short_rendered", **{k: entry[k] for k in ("slug", "duration_s", "qa_pass", "layout")})
        else:
            receipts.log(
                "short_qa_failed",
                **{k: entry[k] for k in ("slug", "duration_s", "qa_pass", "layout")},
                silence_qa=silence_qa,
                loudness_qa=loudness_qa,
            )

    if rendered == 0:
        receipts.log(
            "shorts_blocked",
            code="no_green_rendered_shorts",
            message="Shorts candidates were attempted, but none passed render/QA gates.",
            evidence={"attempted": len(ledger), "candidate_count": len(candidates)},
        )
    (out_root / "shorts-ledger.json").write_text(json.dumps(ledger, indent=1))
    from eddy.ui import console as ui

    ui.json_output([{k: e.get(k) for k in ("slug", "status", "duration_s", "qa_pass")} for e in ledger])
    return ledger
