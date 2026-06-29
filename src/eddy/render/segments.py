"""EDL -> video: per-segment accurate extract with 30ms audio fades, then
lossless -c copy concat (port of vendor render_segment_concat.py).

Hard rules (video-use contract): accurate seek per segment, boundary audio fades
to kill pops, no double-encode at concat."""

from __future__ import annotations

import concurrent.futures
import importlib
import os
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

    def one(job: tuple[int, EdlRange]) -> Path:
        idx, r = job
        # v0.3.1: fold the speed into the cache filename so a resume that newly enables speed-ramp
        # re-renders instead of reusing a stale un-sped segment. 1.0x keeps the old byte-identical
        # name (no churn for the default-off path).
        sp = getattr(r, "speed", 1.0) or 1.0
        seg_out = seg_dir / (f"{idx:04d}.mp4" if abs(sp - 1.0) < 1e-6 else f"{idx:04d}_s{int(round(sp * 1000)):04d}.mp4")
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
    join_qa = _concat_segments_filtergraph(paths, out_path, run_dir, render_cfg, receipts=receipts, proxy=proxy)
    if receipts is not None:
        receipts.log(
            "render",
            out=str(out_path),
            proxy=proxy,
            segments=len(paths),
            edl_duration_s=edl.total_duration_s,
            layout="screen_with_bottom_right_camera" if screen is not None else "single_source",
            join_strategy=join_qa["strategy"],
        )
    return out_path
