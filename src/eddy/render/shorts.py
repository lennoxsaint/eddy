"""Shorts renderer: candidates -> phrase-safe sub-segments -> layout render ->
karaoke captions -> QA ledger.

Layouts (approved standard):
- dual-source: face panel (camera) top, captions, screen panel bottom
- degraded single-composite (primary for composite recordings): one large rounded
  panel above the caption zone on navy
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

from eddy.config import load_config
from eddy.edit.schema import load_decisions
from eddy.loop.receipts import Receipts
from eddy.media.ffmpeg import run_ffmpeg, video_encoder_args
from eddy.media.probe import stream_summary
from eddy.render import layout as L
from eddy.render.captions import burn_captions, caption_events
from eddy.render.long import latest_iteration_dir
from eddy.runs import SourceError, manifest
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
        filter_parts.append(f"[{idx}:v]setpts=PTS-STARTPTS,format=yuv420p[v{idx}]")
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

    candidates = select_short_candidates(decisions.shorts_candidates, cfg.shorts.count, playbook_records)
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
            vw = src_video["width"] or 1920
            vh = src_video["height"] or 1080
            panel_h = min(int(L.PANEL_W * vh / vw), 1100)
            stack_h = panel_h + 56 + L.CAPTION_H
            panel_y = max(60, (L.H - stack_h) // 2)
            caption_y = panel_y + panel_h + 56
            mask = asset_dir / "panel-mask.png"
            _rounded_mask(mask, (L.PANEL_W, panel_h), L.RADIUS)

        seg_paths = []
        for i, (s, e) in enumerate(segs):
            seg_out = asset_dir / "layout-segments" / f"segment-{i:03d}.mp4"
            seg_out.parent.mkdir(exist_ok=True)
            if dual:
                assert screen is not None  # dual layout implies a screen source
                _render_segment_dual(camera, screen, seg_out, s, e, face_mask, screen_mask, src_video["width"], src_video["height"], run_dir)
            else:
                _render_segment_single(camera, seg_out, s, e, mask, panel_h, panel_y, run_dir)
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
        if cfg.audio.studio_sound:
            from eddy.render.audio import studio_sound

            audio_result = studio_sound(final, run_dir, cfg.audio, receipts=receipts)
            if not audio_result.get("quality_gate_pass", False):
                raise RuntimeError(audio_result.get("error") or f"Studio Sound quality gate failed for {slug}")

        final_summary = stream_summary(final)
        silence_qa = silent_motion_gate(final, run_dir, cfg.gates.silence_noise_db, cfg.gates.max_output_silence_s, 0)
        loudness_qa = loudness_gate(final, cfg.audio.target_lufs) if cfg.audio.studio_sound else {"pass": True}
        boundary_pairs = []
        for s, e in segs:
            seg_words = [w for w in words if s <= w["start"] and w["end"] <= e + 0.05]
            if seg_words:
                boundary_pairs.append((seg_words[0]["start"] - s, e - seg_words[-1]["end"]))
        min_pre = min((pre for pre, _post in boundary_pairs), default=0.0)
        min_post = min((post for _pre, post in boundary_pairs), default=0.0)
        fv = final_summary["video"]  # None only if our own render produced no video stream — QA-fail it
        entry = {
            "slug": slug,
            "hook": cand.hook,
            "path": str(final),
            "duration_s": round(final_summary["duration_s"], 1),
            "resolution": f"{fv['width']}x{fv['height']}" if fv else "unknown",
            "segments": len(segs),
            "join_qa": join_qa,
            "caption_events": len(events),
            "sentence_final": ends_on_complete_sentence(words),
            "silence_qa": silence_qa,
            "loudness_qa": loudness_qa,
            "boundary_qa": {"min_pre_handle_s": round(min_pre, 3), "min_post_handle_s": round(min_post, 3)},
            "layout": "dual" if dual else "single_composite",
            "source_provenance": {
                "camera": str(camera),
                "screen": str(screen) if screen else None,
                "requires_dual": screen_declared,
                "used_dual": dual,
            },
            "style_lock": {
                "canvas": f"{L.W}x{L.H}",
                "camera_square": {"x": L.FACE_X, "y": L.FACE_Y, "size": L.FACE_SIZE, "radius": L.FACE_RADIUS},
                "caption_y": L.CAPTION_Y,
                "screen_panel": {"x": L.SCREEN_X, "y": L.SCREEN_Y, "w": L.SCREEN_W, "h": L.SCREEN_H, "radius": L.SCREEN_RADIUS},
                "highlight": L.HIGHLIGHT_BLUE,
            },
            "qa_pass": (
                fv is not None
                and fv["width"] == L.W
                and fv["height"] == L.H
                and (not screen_declared or dual)
                and len(events) > 0
                and final_summary["audio"] is not None
                and ends_on_complete_sentence(words)
                and silence_qa["pass"]
                and loudness_qa["pass"]
                and join_qa["strategy"] == "filtergraph_reencode_concat"
                and not join_qa["concat_demuxer_copy"]
            ),
            "status": "rendered",
        }
        ledger.append(entry)
        rendered += 1
        receipts.log("short_rendered", **{k: entry[k] for k in ("slug", "duration_s", "qa_pass", "layout")})

    (out_root / "shorts-ledger.json").write_text(json.dumps(ledger, indent=1))
    from eddy.ui import console as ui

    ui.json_output([{k: e.get(k) for k in ("slug", "status", "duration_s", "qa_pass")} for e in ledger])
    return ledger
