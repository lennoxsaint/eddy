"""Content-format profiles. The default 14-min length ceiling drives the loop to compress, which is
right for a polished talk but destroys step-by-step tutorials/lessons. A format profile can raise
(effectively disable) the ceiling so long instructional content isn't gutted."""

from __future__ import annotations

FORMATS: dict[str, dict] = {
    "default": {"ceiling_minutes": None},   # use the configured ceiling (14 min)
    "tutorial": {"ceiling_minutes": 600.0},  # ~no ceiling — don't compress a lesson
    "lesson": {"ceiling_minutes": 600.0},
    "longform": {"ceiling_minutes": 600.0},
    "podcast": {"ceiling_minutes": 600.0},
}


def resolve_format(name: str) -> dict:
    return FORMATS.get((name or "default").lower(), FORMATS["default"])
