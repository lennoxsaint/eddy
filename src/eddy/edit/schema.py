"""Editorial artifact schemas.

EditDecisions = Claire schema v1.0 (remove-list, model-facing). Eddy additions
live under `x_eddy` so the shape stays Claire-compatible.
Edl = video-use EDL v1 (keep-list, render-facing). Only the compiler writes it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Tier = Literal["MANDATORY", "RECOMMENDED", "OPTIONAL"]


class Cut(BaseModel):
    start_s: float
    end_s: float
    quote: str = ""  # sanity anchor: roughly the removed text
    reason: str = ""
    tier: Tier = "RECOMMENDED"


class Retake(BaseModel):
    remove_start_s: float
    remove_end_s: float
    kept_take: Literal["last", "earlier"] = "last"
    quote: str = ""
    reason: str = ""


class ProtectedMoment(BaseModel):
    start_s: float
    end_s: float
    reason: str = ""


class ShortsCandidate(BaseModel):
    start_s: float
    end_s: float
    hook: str = ""
    reason: str = ""


class TranscriptCorrection(BaseModel):
    wrong: str
    right: str


class EddyMeta(BaseModel):
    iteration: int = 1
    parent_sha: str = ""
    directive: list[dict] = Field(default_factory=list)
    beats: list[dict] = Field(default_factory=list)  # [{label, start_s, end_s}]


class EditDecisions(BaseModel):
    schema_version: str = "1.0"
    target_runtime_seconds: float = 0
    edit_intensity: str = "medium_clarity"
    transcript_corrections: list[TranscriptCorrection] = Field(default_factory=list)
    retakes: list[Retake] = Field(default_factory=list)
    cuts: list[Cut] = Field(default_factory=list)
    moves: list[dict] = Field(default_factory=list)  # unsupported in v1 renderer; kept for schema parity
    cold_open: dict = Field(default_factory=dict)  # {start_s, end_s, reason}: one payoff clip pulled to the front
    protected_moments: list[ProtectedMoment] = Field(default_factory=list)
    preview_teaser: dict = Field(default_factory=dict)
    shorts_candidates: list[ShortsCandidate] = Field(default_factory=list)
    visual_insert_notes: list[dict] = Field(default_factory=list)
    x_eddy: EddyMeta = Field(default_factory=EddyMeta)

    def all_remove_intervals(self) -> list[tuple[float, float, str]]:
        out = [(r.remove_start_s, r.remove_end_s, "retake") for r in self.retakes]
        out += [(c.start_s, c.end_s, c.tier) for c in self.cuts]
        return sorted(out)


class EdlRange(BaseModel):
    source: str = "camera"
    start: float
    end: float
    beat: str = ""
    quote: str = ""
    reason: str = ""
    start_handle_s: float = 0.0  # silence margin before first word (QA)
    end_handle_s: float = 0.0


class Edl(BaseModel):
    version: int = 1
    sources: dict[str, str]
    ranges: list[EdlRange]
    subtitles: str = ""
    total_duration_s: float = 0.0

    def to_benchmark_format(self, slug: str = "", title: str = "") -> dict:
        """Prior-pipeline edit-decisions.json shape, for objective diffs."""
        return {
            "slug": slug,
            "title": title,
            "source_video": next(iter(self.sources.values()), ""),
            "ranges": [
                {
                    "start": r.start,
                    "end": r.end,
                    "duration": round(r.end - r.start, 3),
                    "beat": r.beat,
                    "reason": r.reason,
                }
                for r in self.ranges
            ],
        }


def load_decisions(path: Path) -> EditDecisions:
    return EditDecisions.model_validate_json(Path(path).read_text())


def save(model: BaseModel, path: Path) -> None:
    Path(path).write_text(json.dumps(model.model_dump(), indent=1))


def load_edl(path: Path) -> Edl:
    return Edl.model_validate_json(Path(path).read_text())
