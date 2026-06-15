"""EDL -> video: per-segment accurate extract with 30ms audio fades, then
lossless -c copy concat (port of vendor render_segment_concat.py).

Hard rules (video-use contract): accurate seek per segment, boundary audio fades
to kill pops, no double-encode at concat."""

from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path

from eddy.config import RenderConfig
from eddy.edit.schema import Edl, EdlRange
from eddy.media.ffmpeg import concat_quote, run_ffmpeg, video_encoder_args

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

    vf = "fps=30,setpts=PTS-STARTPTS"
    if proxy_height:
        vf = f"scale=-2:{proxy_height}," + vf
    # v0.3.1 time-compression: the afades run on the source-rate stream (st in source seconds),
    # so atempo is inserted AFTER them and the fade-out st needs no adjustment. setpts=PTS/speed
    # compresses the video timeline to match. Both streams end at duration/speed.
    af = f"afade=t=in:st=0:d={fade_s:.3f},afade=t=out:st={max(0.0, duration - fade_s):.3f}:d={fade_s:.3f},asetpts=PTS-STARTPTS"
    if abs(speed - 1.0) > 1e-6:
        # setpts compresses the timeline; the trailing fps=30 re-normalizes the sped video back
        # to CFR 30 (dropping the now-redundant frames) so every segment shares one rate/timebase
        # for the lossless -c copy concat AND the video lands on the same duration as the atempo
        # audio. atempo follows the afades (which run on the source-rate stream, st in source secs).
        vf = f"{vf},setpts=PTS/{speed:.6f},fps=30"
        af = (
            f"afade=t=in:st=0:d={fade_s:.3f},"
            f"afade=t=out:st={max(0.0, duration - fade_s):.3f}:d={fade_s:.3f},"
            f"atempo={speed:.6f},asetpts=PTS-STARTPTS"
        )

    # The -t cap is an OUTPUT-duration limit. With setpts=PTS/speed, ffmpeg reads (cap * speed)
    # of input to fill it, so the cap must be the OUTPUT length duration/speed — otherwise a sped
    # segment reads `speed`x more source and emits no net compression (it stays `duration` long).
    out_t = duration / speed
    args = ["-ss", f"{seek_start:.3f}", "-i", str(source)]
    if output_seek > 0:
        args += ["-ss", f"{output_seek:.3f}"]
    args += ["-t", f"{out_t:.3f}", "-map", "0:v:0", "-map", "0:a:0", "-vf", vf, "-af", af]
    if proxy_height:
        args += ["-c:v", "libx264", "-preset", proxy_preset, "-crf", "28", "-c:a", "aac", "-b:a", "96k"]
    else:
        args += [
            *video_encoder_args("7000k"),  # includes -pix_fmt yuv420p
            "-c:a", "aac", "-b:a", "160k",
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
        run_ffmpeg(
            _segment_args(
                source, partial, r.start, r.end, fade_s,
                render_cfg.proxy_height if proxy else None,
                render_cfg.proxy_preset,
                getattr(r, "speed", 1.0),
            ),
            run_dir=run_dir,
            receipts=None,  # per-segment receipts are noise; the concat logs the render
        )
        os.replace(partial, seg_out)
        return seg_out

    jobs = list(enumerate(edl.ranges))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        paths = list(pool.map(one, jobs))

    list_path = seg_dir / "concat.txt"
    list_path.write_text("\n".join(f"file {concat_quote(p)}" for p in paths) + "\n")
    run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", "-movflags", "+faststart", str(out_path)],
        run_dir=run_dir,
        receipts=receipts,
    )
    if receipts is not None:
        receipts.log("render", out=str(out_path), proxy=proxy, segments=len(paths), edl_duration_s=edl.total_duration_s)
    return out_path
