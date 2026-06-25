from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from PIL import Image, ImageDraw

    from eddy.ui import pixels, sprite
except ModuleNotFoundError as exc:  # pragma: no cover - operator guidance.
    raise SystemExit(
        "Missing Eddy development dependencies. Run this with the repo environment, for example: "
        ".venv/bin/python scripts/generate_plugin_assets.py"
    ) from exc

GOLD = (248, 190, 52, 255)
DARK = (12, 10, 8, 255)
WARM_DARK = (24, 18, 12, 255)


def _render_bitmap(bitmap: list[str], *, scale: int) -> Image.Image:
    width = pixels.width(bitmap)
    height = len(bitmap)
    image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(bitmap):
        for x, key in enumerate(row.ljust(width, ".")):
            rgb = pixels.PALETTE.get(key)
            if rgb is None:
                continue
            draw.rectangle(
                [x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1],
                fill=(*rgb, 255),
            )
    return image


def _center(base: Image.Image, item: Image.Image, *, y_offset: int = 0) -> None:
    x = (base.width - item.width) // 2
    y = (base.height - item.height) // 2 + y_offset
    base.alpha_composite(item, (x, y))


def make_composer_icon(path: Path) -> None:
    base = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    eagle = _render_bitmap(sprite.frame("success", small=False), scale=18)
    _center(base, eagle, y_offset=6)
    path.parent.mkdir(parents=True, exist_ok=True)
    base.save(path)


def make_logo(path: Path) -> None:
    base = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([64, 64, 960, 960], radius=192, fill=DARK, outline=GOLD, width=28)
    draw.rounded_rectangle([112, 112, 912, 912], radius=152, outline=WARM_DARK, width=10)
    eagle = _render_bitmap(sprite.frame("success", small=False), scale=30)
    _center(base, eagle, y_offset=16)
    path.parent.mkdir(parents=True, exist_ok=True)
    base.save(path)


def main() -> None:
    assets = ROOT / "plugins" / "eddy" / "assets"
    make_composer_icon(assets / "eddy-eagle-icon.png")
    make_logo(assets / "eddy-eagle-logo.png")


if __name__ == "__main__":
    main()
