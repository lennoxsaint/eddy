"""EDL -> video: per-segment accurate extract with 30ms audio fades, then
lossless -c copy concat (port of vendor render_segment_concat.py).

Hard rules (video-use contract): accurate seek per segment, boundary audio fades
to kill pops, no double-encode at concat."""

from __future__ import annotations

import concurrent.futures
import hashlib
import importlib
import json
import os
import textwrap
from pathlib import Path
from typing import Any

from eddy.config import RenderConfig
from eddy.edit.schema import Edl, EdlRange
from eddy.media.ffmpeg import concat_quote, run_ffmpeg, video_encoder_args

PILImage: Any
PILImageDraw: Any
try:
    PILImage = importlib.import_module("PIL.Image")
    PILImageDraw = importlib.import_module("PIL.ImageDraw")
except Exception:  # pragma: no cover - pillow is a runtime dependency, but keep import-safe
    PILImage = None
    PILImageDraw = None

SEEK_PREROLL_S = 2.0
_FONT_REGULAR = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
_FONT_BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")


def _segment_cache_fingerprint(
    r: EdlRange,
    *,
    render_cfg: RenderConfig,
    source: Path,
    screen: Path | None,
    proxy: bool,
    proxy_height: int | None,
) -> str:
    payload = {
        "start": round(float(r.start), 3),
        "end": round(float(r.end), 3),
        "speed": round(float(getattr(r, "speed", 1.0) or 1.0), 6),
        "source": str(source),
        "screen": str(screen) if screen else "",
        "proxy": proxy,
        "proxy_height": proxy_height,
        "long_camera_size": render_cfg.long_camera_size,
        "long_camera_radius": render_cfg.long_camera_radius,
        "long_camera_margin": render_cfg.long_camera_margin,
        "boundary_fade_ms": render_cfg.boundary_fade_ms,
        "final_crf": render_cfg.final_crf,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def _render_cache_fingerprint(
    edl: Edl,
    *,
    render_cfg: RenderConfig,
    source: Path,
    screen: Path | None,
    proxy: bool,
    proxy_height: int | None,
) -> str:
    payload = {
        "ranges": [
            {
                "start": round(float(r.start), 3),
                "end": round(float(r.end), 3),
                "speed": round(float(getattr(r, "speed", 1.0) or 1.0), 6),
            }
            for r in edl.ranges
        ],
        "source": str(source),
        "screen": str(screen) if screen else "",
        "proxy": proxy,
        "proxy_height": proxy_height,
        "long_camera_size": render_cfg.long_camera_size,
        "long_camera_radius": render_cfg.long_camera_radius,
        "long_camera_margin": render_cfg.long_camera_margin,
        "boundary_fade_ms": render_cfg.boundary_fade_ms,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def _filter_escape(value: str) -> str:
    """Escape a string for use as a single ffmpeg filter option value."""
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _normalise_visual_insert_notes(notes: list[dict] | None) -> list[dict]:
    out: list[dict] = []
    for note in notes or []:
        if not isinstance(note, dict):
            continue
        text = str(note.get("text") or note.get("note") or note.get("title") or "").strip()
        if not text:
            continue
        start_value = note.get("out_start_s", note.get("start_s", note.get("at_s")))
        if start_value is None:
            continue
        try:
            start = float(start_value)
        except (TypeError, ValueError):
            continue
        try:
            end = float(note.get("out_end_s", note.get("end_s", start + float(note.get("duration_s", 4.0)))))
        except (TypeError, ValueError):
            end = start + 4.0
        start = max(0.0, start)
        end = max(start + 0.5, end)
        out.append({"out_start_s": start, "out_end_s": end, "text": text})
    return out


def _visual_insert_filtergraph(
    notes: list[dict] | None,
    work_dir: Path,
    proxy: bool = False,
) -> tuple[str, int]:
    """Build a drawtext chain for timed proof/context cards.

    The cards are intentionally visual-only: they can clarify a screen-share or CTA, but they do
    not alter source audio or EDL timing.
    """
    normalised = _normalise_visual_insert_notes(notes)
    if not normalised:
        return "[0:v]setpts=PTS-STARTPTS[v]", 0

    work_dir.mkdir(parents=True, exist_ok=True)
    font = _FONT_REGULAR if _FONT_REGULAR.exists() else _FONT_BOLD
    fontfile = _filter_escape(str(font)) if font.exists() else ""
    fontsize = 22 if proxy else 44
    line_spacing = 4 if proxy else 8
    wrap_cols = 58 if proxy else 68
    filters: list[str] = ["[0:v]setpts=PTS-STARTPTS[v0]"]
    current = "v0"
    for idx, note in enumerate(normalised):
        wrapped = "\n".join(textwrap.wrap(note["text"], width=wrap_cols, break_long_words=False))
        text_path = work_dir / f"visual-insert-{idx:02d}.txt"
        text_path.write_text(wrapped + "\n")
        enable = f"between(t\\,{note['out_start_s']:.3f}\\,{note['out_end_s']:.3f})"
        box_label = f"vb{idx}"
        out_label = "v" if idx == len(normalised) - 1 else f"v{idx + 1}"
        filters.append(
            f"[{current}]drawbox=x=0:y=ih*0.780:w=iw:h=ih*0.160:"
            f"color=black@0.72:t=fill:enable='{enable}'[{box_label}]"
        )
        drawtext_options = [
            f"textfile={_filter_escape(str(text_path))}",
            "x=(w-text_w)/2",
            "y=h*0.780+(h*0.160-text_h)/2",
            f"fontsize={fontsize}",
            "fontcolor=white",
            f"line_spacing={line_spacing}",
            f"enable='{enable}'",
        ]
        if fontfile:
            drawtext_options.insert(0, f"fontfile={fontfile}")
        filters.append(f"[{box_label}]drawtext=" + ":".join(drawtext_options) + f"[{out_label}]")
        current = out_label
    return ";".join(filters), len(normalised)


def _apply_visual_insert_notes(
    source_path: Path,
    out_path: Path,
    run_dir: Path,
    render_cfg: RenderConfig,
    notes: list[dict] | None,
    receipts=None,
    proxy: bool = False,
) -> int:
    graph, count = _visual_insert_filtergraph(notes, out_path.parent / f"{out_path.stem}_visual_insert_text", proxy)
    if not count:
        if source_path != out_path:
            os.replace(source_path, out_path)
        return 0
    if proxy:
        video_args = ["-c:v", "libx264", "-preset", render_cfg.proxy_preset, "-crf", "28", "-pix_fmt", "yuv420p"]
    else:
        video_args = [*video_encoder_args("7000k")]
    run_ffmpeg(
        [
            "-i", str(source_path),
            "-filter_complex", graph,
            "-map", "[v]", "-map", "0:a?",
            *video_args,
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ],
        run_dir=run_dir,
        receipts=receipts,
    )
    return count


def _segment_args(
    source: Path,
    out: Path,
    start: float,
    end: float,
    fade_s: float,
    proxy_height: int | None,
    proxy_preset: str,
    speed: float = 1.0,
) -> list[str]:
    duration = max(0.05, end - start)
    seek_start = max(0.0, start - SEEK_PREROLL_S)
    output_seek = start - seek_start
    speed = speed or 1.0

    vf = f"trim=start={output_seek:.3f}:duration={duration:.3f},setpts=PTS-STARTPTS"
    if proxy_height:
        vf += f",scale=-2:{proxy_height}"
    vf += ",fps=30"
    # v0.3.1 time-compression: the afades run on the source-rate stream (st in source seconds),
    # so atempo is inserted AFTER them and the fade-out st needs no adjustment. setpts=PTS/speed
    # compresses the video timeline to match. Both streams end at duration/speed.
    af = (
        f"atrim=start={output_seek:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fade_s:.3f},"
        f"afade=t=out:st={max(0.0, duration - fade_s):.3f}:d={fade_s:.3f}"
    )
    if abs(speed - 1.0) > 1e-6:
        # setpts compresses the timeline; the trailing fps=30 re-normalizes the sped video back
        # to CFR 30 (dropping the now-redundant frames) so every segment shares one rate/timebase
        # for the lossless -c copy concat AND the video lands on the same duration as the atempo
        # audio. atempo follows the afades (which run on the source-rate stream, st in source secs).
        vf = vf.replace("setpts=PTS-STARTPTS", f"setpts=(PTS-STARTPTS)/{speed:.6f}")
        af = (
            f"atrim=start={output_seek:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade_s:.3f},"
            f"afade=t=out:st={max(0.0, duration - fade_s):.3f}:d={fade_s:.3f},"
            f"atempo={speed:.6f},asetpts=PTS-STARTPTS"
        )

    input_t = output_seek + duration
    args = ["-ss", f"{seek_start:.3f}", "-t", f"{input_t:.3f}", "-i", str(source)]
    args += ["-map", "0:v:0", "-map", "0:a:0", "-vf", vf, "-af", af]
    if proxy_height:
        args += [
            "-c:v", "libx264", "-preset", proxy_preset, "-crf", "28", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
        ]
    else:
        args += [
            *video_encoder_args("7000k"),  # includes -pix_fmt yuv420p
            "-c:a", "aac", "-b:a", "160k",
        ]
    args += ["-movflags", "+faststart", str(out)]
    return args


def _rounded_mask(path: Path, size: tuple[int, int], radius: int) -> Path:
    if PILImage is None or PILImageDraw is None:
        raise RuntimeError("Pillow is required for rounded camera masks")
    if path.exists():
        return path
    img = PILImage.new("L", size, 0)
    PILImageDraw.Draw(img).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    img.save(path)
    return path


def _segment_args_dual(
    camera: Path,
    screen: Path,
    mask: Path,
    out: Path,
    start: float,
    end: float,
    fade_s: float,
    render_cfg: RenderConfig,
    proxy_height: int | None,
    proxy_preset: str,
    speed: float = 1.0,
) -> list[str]:
    duration = max(0.05, end - start)
    seek_start = max(0.0, start - SEEK_PREROLL_S)
    output_seek = start - seek_start
    speed = speed or 1.0

    out_h = proxy_height or 1080
    out_w = int(round(out_h * 16 / 9))
    if out_w % 2:
        out_w += 1
    cam_size = max(80, int(round(render_cfg.long_camera_size * out_h / 1080)))
    margin = max(0, int(round(render_cfg.long_camera_margin * out_h / 1080)))
    cam_x = out_w - cam_size - margin
    cam_y = out_h - cam_size - margin
    crop_expr = "min(iw\\,ih)"
    video_setpts = "setpts=PTS-STARTPTS"
    audio_tail = ""
    if abs(speed - 1.0) > 1e-6:
        video_setpts = f"setpts=(PTS-STARTPTS)/{speed:.6f}"
        audio_tail = f",atempo={speed:.6f},asetpts=PTS-STARTPTS"
    graph = (
        f"[0:v]trim=start={output_seek:.3f}:duration={duration:.3f},{video_setpts},"
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=rgba[screen];"
        f"[1:v]trim=start={output_seek:.3f}:duration={duration:.3f},{video_setpts},"
        f"crop={crop_expr}:{crop_expr}:(iw-{crop_expr})/2:0,"
        f"scale={cam_size}:{cam_size},setsar=1,fps=30,format=rgba[camraw];"
        "[camraw][2:v]alphamerge[cam];"
        f"[screen][cam]overlay={cam_x}:{cam_y}:format=auto,setpts=PTS-STARTPTS[v];"
        f"[1:a]atrim=start={output_seek:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fade_s:.3f},"
        f"afade=t=out:st={max(0.0, duration - fade_s):.3f}:d={fade_s:.3f}{audio_tail}[a]"
    )
    input_t = output_seek + duration
    args = [
        "-ss", f"{seek_start:.3f}", "-t", f"{input_t:.3f}", "-i", str(screen),
        "-ss", f"{seek_start:.3f}", "-t", f"{input_t:.3f}", "-i", str(camera),
    ]
    args += ["-i", str(mask)]
    args += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]"]
    if proxy_height:
        args += [
            "-c:v", "libx264", "-preset", proxy_preset, "-crf", "28", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
        ]
    else:
        args += [*video_encoder_args("7000k"), "-c:a", "aac", "-b:a", "160k"]
    args += ["-movflags", "+faststart", str(out)]
    return args


def _concat_segments_filtergraph(
    paths: list[Path],
    out_path: Path,
    run_dir: Path,
    render_cfg: RenderConfig,
    receipts=None,
    proxy: bool = False,
) -> dict:
    if not paths:
        raise ValueError("no rendered segments to join")

    inputs: list[str] = []
    filter_parts: list[str] = []
    concat_labels: list[str] = []
    for idx, path in enumerate(paths):
        inputs.extend(["-i", str(path)])
        filter_parts.append(f"[{idx}:v]setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{idx}]")
        filter_parts.append(f"[{idx}:a]asetpts=PTS-STARTPTS[a{idx}]")
        concat_labels.append(f"[v{idx}][a{idx}]")

    graph = ";".join(
        filter_parts + ["".join(concat_labels) + f"concat=n={len(paths)}:v=1:a=1[v][a]"]
    )
    if proxy:
        video_args = ["-c:v", "libx264", "-preset", render_cfg.proxy_preset, "-crf", "28", "-pix_fmt", "yuv420p"]
        audio_args = ["-c:a", "aac", "-b:a", "128k"]
    else:
        video_args = [*video_encoder_args("7000k")]
        audio_args = ["-c:a", "aac", "-b:a", "160k"]

    run_ffmpeg(
        [
            *inputs,
            "-filter_complex", graph,
            "-map", "[v]", "-map", "[a]",
            *video_args, "-r", "30",
            *audio_args, "-movflags", "+faststart", str(out_path),
        ],
        run_dir=run_dir,
        receipts=receipts,
    )
    return {
        "strategy": "filtergraph_reencode_concat",
        "reencoded": True,
        "segment_count": len(paths),
        "concat_demuxer_copy": False,
    }


def render_edl(
    edl: Edl,
    out_path: Path,
    run_dir: Path,
    render_cfg: RenderConfig,
    receipts=None,
    proxy: bool = False,
    workers: int = 4,
    visual_insert_notes: list[dict] | None = None,
) -> Path:
    source = Path(edl.sources.get("camera") or next(iter(edl.sources.values())))
    screen = Path(edl.sources["screen"]) if edl.sources.get("screen") else None
    seg_dir = out_path.parent / (out_path.stem + "_segments")
    seg_dir.mkdir(parents=True, exist_ok=True)
    fade_s = render_cfg.boundary_fade_ms / 1000
    mask = None
    if screen is not None:
        proxy_h = render_cfg.proxy_height if proxy else 1080
        cam_size = max(80, int(round(render_cfg.long_camera_size * proxy_h / 1080)))
        radius = max(10, int(round(render_cfg.long_camera_radius * proxy_h / 1080)))
        mask = _rounded_mask(seg_dir / f"camera-mask-{cam_size}-r{radius}.png", (cam_size, cam_size), radius)
        if receipts is not None:
            receipts.log(
                "long_style_lock",
                layout="screen_with_bottom_right_camera",
                camera_square={"size": cam_size, "radius": radius, "margin": render_cfg.long_camera_margin},
            )
    render_fingerprint = _render_cache_fingerprint(
        edl,
        render_cfg=render_cfg,
        source=source,
        screen=screen,
        proxy=proxy,
        proxy_height=render_cfg.proxy_height if proxy else None,
    )

    def one(job: tuple[int, EdlRange]) -> Path:
        idx, r = job
        # v0.3.1: fold the speed into the cache filename so a resume that newly enables speed-ramp
        # re-renders instead of reusing a stale un-sped segment. 1.0x keeps the old byte-identical
        # name (no churn for the default-off path).
        sp = getattr(r, "speed", 1.0) or 1.0
        fingerprint = _segment_cache_fingerprint(
            r,
            render_cfg=render_cfg,
            source=source,
            screen=screen,
            proxy=proxy,
            proxy_height=render_cfg.proxy_height if proxy else None,
        )
        seg_out = seg_dir / (
            f"{idx:04d}_{fingerprint}.mp4"
            if abs(sp - 1.0) < 1e-6
            else f"{idx:04d}_s{int(round(sp * 1000)):04d}_{fingerprint}.mp4"
        )
        if seg_out.exists() and seg_out.stat().st_size > 1024:
            return seg_out
        # render to a .partial sibling, then os.replace on success: a SIGKILL/Ctrl-C mid-render
        # leaves a .partial (ignored by the cache check above), never a truncated final segment
        # that --resume would blindly reuse.
        partial = seg_out.with_name(f"{seg_out.stem}.partial{seg_out.suffix}")
        if screen is not None and mask is not None:
            args = _segment_args_dual(
                source, screen, mask, partial, r.start, r.end, fade_s, render_cfg,
                render_cfg.proxy_height if proxy else None, render_cfg.proxy_preset, getattr(r, "speed", 1.0),
            )
        else:
            args = _segment_args(
                source, partial, r.start, r.end, fade_s,
                render_cfg.proxy_height if proxy else None,
                render_cfg.proxy_preset,
                getattr(r, "speed", 1.0),
            )
        run_ffmpeg(args, run_dir=run_dir, receipts=None)
        os.replace(partial, seg_out)
        return seg_out

    jobs = list(enumerate(edl.ranges))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        paths = list(pool.map(one, jobs))

    list_path = seg_dir / "concat.txt"
    list_path.write_text("\n".join(f"file {concat_quote(p.resolve())}" for p in paths) + "\n")
    notes = _normalise_visual_insert_notes(visual_insert_notes)
    concat_out = out_path if not notes else out_path.with_name(f"{out_path.stem}.base{out_path.suffix}")
    join_qa = _concat_segments_filtergraph(paths, concat_out, run_dir, render_cfg, receipts=receipts, proxy=proxy)
    visual_insert_count = _apply_visual_insert_notes(
        concat_out, out_path, run_dir, render_cfg, notes, receipts=receipts, proxy=proxy,
    )
    if concat_out != out_path and concat_out.exists():
        concat_out.unlink()
    if receipts is not None:
        receipts.log(
            "render",
            out=str(out_path),
            proxy=proxy,
            segments=len(paths),
            edl_duration_s=edl.total_duration_s,
            layout="screen_with_bottom_right_camera" if screen is not None else "single_source",
            join_strategy=join_qa["strategy"],
            segment_cache_fingerprint=render_fingerprint,
            visual_inserts=visual_insert_count,
        )
    return out_path
