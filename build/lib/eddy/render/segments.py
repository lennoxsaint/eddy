"""EDL -> video: per-segment accurate extract with 30ms audio fades, then
lossless -c copy concat (port of vendor render_segment_concat.py).

Hard rules (video-use contract): accurate seek per segment, boundary audio fades
to kill pops, no double-encode at concat."""

from __future__ import annotations

import concurrent.futures
import shlex
from pathlib import Path

from eddy.config import RenderConfig
from eddy.edit.schema import Edl
from eddy.media.ffmpeg import run_ffmpeg

SEEK_PREROLL_S = 2.0


def _segment_args(
    source: Path,
    out: Path,
    start: float,
    end: float,
    fade_s: float,
    proxy_height: int | None,
    proxy_preset: str,
) -> list[str]:
    duration = max(0.05, end - start)
    seek_start = max(0.0, start - SEEK_PREROLL_S)
    output_seek = start - seek_start

    vf = "fps=30,setpts=PTS-STARTPTS"
    if proxy_height:
        vf = f"scale=-2:{proxy_height}," + vf
    af = f"afade=t=in:st=0:d={fade_s:.3f},afade=t=out:st={max(0.0, duration - fade_s):.3f}:d={fade_s:.3f},asetpts=PTS-STARTPTS"

    args = ["-ss", f"{seek_start:.3f}", "-i", str(source)]
    if output_seek > 0:
        args += ["-ss", f"{output_seek:.3f}"]
    args += ["-t", f"{duration:.3f}", "-map", "0:v:0", "-map", "0:a:0", "-vf", vf, "-af", af]
    if proxy_height:
        args += ["-c:v", "libx264", "-preset", proxy_preset, "-crf", "28", "-c:a", "aac", "-b:a", "96k"]
    else:
        args += [
            "-c:v", "h264_videotoolbox", "-allow_sw", "1", "-b:v", "7000k",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        ]
    args += ["-movflags", "+faststart", str(out)]
    return args


def render_edl(
    edl: Edl,
    out_path: Path,
    run_dir: Path,
    render_cfg: RenderConfig,
    receipts=None,
    proxy: bool = False,
    workers: int = 4,
) -> Path:
    source = Path(next(iter(edl.sources.values())))
    seg_dir = out_path.parent / (out_path.stem + "_segments")
    seg_dir.mkdir(parents=True, exist_ok=True)
    fade_s = render_cfg.boundary_fade_ms / 1000

    def one(job: tuple[int, object]) -> Path:
        idx, r = job
        seg_out = seg_dir / f"{idx:04d}.mp4"
        if seg_out.exists() and seg_out.stat().st_size > 1024:
            return seg_out
        run_ffmpeg(
            _segment_args(
                source, seg_out, r.start, r.end, fade_s,
                render_cfg.proxy_height if proxy else None,
                render_cfg.proxy_preset,
            ),
            run_dir=run_dir,
            receipts=None,  # per-segment receipts are noise; the concat logs the render
        )
        return seg_out

    jobs = list(enumerate(edl.ranges))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        paths = list(pool.map(one, jobs))

    list_path = seg_dir / "concat.txt"
    list_path.write_text("\n".join(f"file {shlex.quote(str(p))}" for p in paths) + "\n")
    run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", "-movflags", "+faststart", str(out_path)],
        run_dir=run_dir,
        receipts=receipts,
    )
    if receipts is not None:
        receipts.log("render", out=str(out_path), proxy=proxy, segments=len(paths), edl_duration_s=edl.total_duration_s)
    return out_path
