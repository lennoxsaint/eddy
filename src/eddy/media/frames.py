"""Frame extraction: contact sheets at cut boundaries, sharp face-reference frames."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

from eddy import log
from eddy.edit.schema import Edl
from eddy.media.ffmpeg import run_ffmpeg


def extract_frame(video: Path, at_s: float, out: Path, run_dir: Path, height: int = 360) -> Path:
    run_ffmpeg(
        ["-ss", f"{max(0.0, at_s):.3f}", "-i", str(video), "-frames:v", "1",
         "-vf", f"scale=-2:{height}", str(out)],
        run_dir=run_dir,
    )
    return out


def boundary_contact_sheet(video: Path, edl: Edl, out: Path, run_dir: Path, offset_s: float = 0.4) -> Path:
    """Tile (boundary-before, boundary-after) frame pairs around every splice
    on the OUTPUT video timeline."""
    splices = []
    cursor = 0.0
    for r in edl.ranges[:-1]:
        cursor += r.end - r.start
        splices.append(cursor)
    if not splices:
        splices = [0.0]

    tmp = out.parent / (out.stem + "_frames")
    tmp.mkdir(parents=True, exist_ok=True)
    tiles = []
    for i, t in enumerate(splices):
        for tag, at in (("a", t - offset_s), ("b", t + offset_s)):
            f = tmp / f"{i:03d}{tag}.jpg"
            try:
                extract_frame(video, at, f, run_dir)
                tiles.append(f)
            except Exception as exc:
                log.debug("contact-sheet frame at %.2fs failed: %s", at, exc)

    if not tiles:
        raise RuntimeError("no frames extracted for contact sheet")
    imgs = [Image.open(t) for t in tiles]
    w, h = imgs[0].size
    cols = 4
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (10, 10, 20))
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(out, quality=80)
    return out


def laplacian_sharpness(img: Image.Image) -> float:
    gray = img.convert("L").filter(ImageFilter.FIND_EDGES)
    hist = gray.histogram()
    total = sum(hist)
    mean = sum(i * c for i, c in enumerate(hist)) / max(1, total)
    var = sum(c * (i - mean) ** 2 for i, c in enumerate(hist)) / max(1, total)
    return var


def face_reference_frames(
    video: Path, moments_s: list[float], out_dir: Path, run_dir: Path, top_n: int = 5
) -> list[Path]:
    """Extract candidate frames at given moments, return the sharpest N at full res."""
    out_dir.mkdir(parents=True, exist_ok=True)
    scored: list[tuple[float, float]] = []
    for t in moments_s:
        probe_path = out_dir / f"probe-{t:.1f}.jpg"
        try:
            extract_frame(video, t, probe_path, run_dir, height=270)
            scored.append((laplacian_sharpness(Image.open(probe_path)), t))
        except Exception as exc:
            log.debug("face-reference frame at %.2fs failed: %s", t, exc)
            continue
        finally:
            probe_path.unlink(missing_ok=True)
    scored.sort(reverse=True)

    refs = []
    for _score, t in scored[:top_n]:
        f = out_dir / f"ref-{t:.1f}.jpg"
        run_ffmpeg(["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(f)], run_dir=run_dir)
        refs.append(f)
    return refs
