"""Studio Sound profiles and profile-name resolution."""

from __future__ import annotations

from dataclasses import dataclass

from eddy.config import AudioConfig


@dataclass(frozen=True)
class StudioSoundProfile:
    name: str
    dry_mix: float
    click_passes: int
    deesser_passes: int
    denoise: bool
    presence_gain_db: float
    compressor_ratio: float
    source_mode: str
    warm_low_shelf_db: float
    box_cut_db: float
    room_cut_db: float
    notes: str


STUDIO_SOUND_PROFILES: dict[str, StudioSoundProfile] = {
    "source_reference": StudioSoundProfile(
        name="source_reference",
        dry_mix=1.0,
        click_passes=0,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.0,
        compressor_ratio=1.0,
        source_mode="reference",
        warm_low_shelf_db=0.0,
        box_cut_db=0.0,
        room_cut_db=0.0,
        notes="Do-not-harm candidate: preserve source/reference audio when cleanup makes it worse.",
    ),
    "warm_room_tame": StudioSoundProfile(
        name="warm_room_tame",
        dry_mix=0.52,
        click_passes=1,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.4,
        compressor_ratio=1.8,
        source_mode="raw",
        warm_low_shelf_db=2.2,
        box_cut_db=-2.0,
        room_cut_db=-1.8,
        notes="Source-first candidate: warmer/deeper voice, modest room cuts, very light click repair.",
    ),
    "warm_deep_tame": StudioSoundProfile(
        name="warm_deep_tame",
        dry_mix=0.50,
        click_passes=1,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.2,
        compressor_ratio=1.8,
        source_mode="raw",
        warm_low_shelf_db=3.0,
        box_cut_db=-2.3,
        room_cut_db=-2.1,
        notes="Source-first candidate: deeper/closer voice with stronger low-body support and room cuts.",
    ),
    "warm_click_tame": StudioSoundProfile(
        name="warm_click_tame",
        dry_mix=0.42,
        click_passes=2,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.7,
        compressor_ratio=2.0,
        source_mode="raw",
        warm_low_shelf_db=2.0,
        box_cut_db=-2.0,
        room_cut_db=-2.2,
        notes="Source-first candidate with stronger click repair while keeping the room natural.",
    ),
    "warm_model_10": StudioSoundProfile(
        name="warm_model_10",
        dry_mix=0.90,
        click_passes=1,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.4,
        compressor_ratio=1.8,
        source_mode="heavy",
        warm_low_shelf_db=1.8,
        box_cut_db=-1.6,
        room_cut_db=-1.6,
        notes="Mostly source audio with a tiny model-enhanced layer underneath; fails if it adds echo.",
    ),
    "natural_voice": StudioSoundProfile(
        name="natural_voice",
        dry_mix=0.28,
        click_passes=1,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=1.2,
        compressor_ratio=2.0,
        source_mode="heavy",
        warm_low_shelf_db=0.0,
        box_cut_db=0.0,
        room_cut_db=0.0,
        notes="Least processed candidate: keeps room/voice texture, repairs obvious clicks.",
    ),
    "click_rescue": StudioSoundProfile(
        name="click_rescue",
        dry_mix=0.18,
        click_passes=2,
        deesser_passes=1,
        denoise=False,
        presence_gain_db=1.8,
        compressor_ratio=2.4,
        source_mode="heavy",
        warm_low_shelf_db=0.0,
        box_cut_db=0.0,
        room_cut_db=0.0,
        notes="Middle candidate: stronger mouth-click cleanup without FFT denoise.",
    ),
    "broadcast_clean": StudioSoundProfile(
        name="broadcast_clean",
        dry_mix=0.10,
        click_passes=2,
        deesser_passes=2,
        denoise=True,
        presence_gain_db=2.5,
        compressor_ratio=3.0,
        source_mode="heavy",
        warm_low_shelf_db=0.0,
        box_cut_db=0.0,
        room_cut_db=0.0,
        notes="Most processed candidate: reserved for noisy/echo-heavy source audio.",
    ),
    "surgical_click_rescue": StudioSoundProfile(
        name="surgical_click_rescue",
        dry_mix=0.06,
        click_passes=3,
        deesser_passes=2,
        denoise=True,
        presence_gain_db=2.2,
        compressor_ratio=2.8,
        source_mode="heavy",
        warm_low_shelf_db=0.0,
        box_cut_db=0.0,
        room_cut_db=-1.4,
        notes="Most click-focused candidate: use when mouth clicks survive balanced cleanup.",
    ),
}


def _studio_sound_profile_names(cfg: AudioConfig) -> list[str]:
    profile = cfg.studio_sound_profile.strip().lower()
    aliases = {
        "strong_studio_sound": "broadcast_clean",
        "strong": "broadcast_clean",
        "balanced": "click_rescue",
        "natural": "natural_voice",
        "source": "source_reference",
        "reference": "source_reference",
        "preserve": "source_reference",
        "warm": "warm_room_tame",
        "deep": "warm_deep_tame",
        "room_tame": "warm_room_tame",
        "warm_click": "warm_click_tame",
    }
    if profile == "auto":
        names = [aliases.get(p.strip().lower(), p.strip().lower()) for p in cfg.studio_sound_candidate_profiles]
    else:
        names = [aliases.get(profile, profile)]
    valid = [name for name in names if name in STUDIO_SOUND_PROFILES]
    return valid or ["click_rescue"]
