"""ffmpeg filter-chain construction for Studio Sound."""

from __future__ import annotations

import functools
import re
import subprocess

from eddy import log
from eddy.config import AudioConfig
from eddy.media.ffmpeg import FFMPEG

from ._profiles import StudioSoundProfile


@functools.lru_cache(maxsize=1)
def _available_audio_filters() -> frozenset[str]:
    # Read-only capability probe: no output path to guard and it must degrade to an empty set rather
    # than raise, so it deliberately bypasses run_ffmpeg (which adds -y and raises on failure).
    try:
        proc = subprocess.run([FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=15)
    except Exception as exc:
        log.debug("audio filter enumeration failed: %s", exc)
        return frozenset()
    names = set(re.findall(r"^\s*[A-Z. ]{2,8}\s+([a-z0-9_]+)\s+", proc.stdout, re.MULTILINE))
    return frozenset(names)


def _speech_eq(cfg: AudioConfig) -> str:
    filters = _available_audio_filters()
    chain = [f"highpass=f={cfg.highpass_hz}"]
    if "afftdn" in filters:
        chain.append("afftdn=nf=-30")
    if cfg.mouth_click_cleanup:
        # These filters are optional across ffmpeg builds. Use them when present, skip silently when
        # absent so the studio-sound pass remains portable.
        if "adeclick" in filters:
            chain.append("adeclick")
            chain.append("adeclick")
        if "deesser" in filters:
            chain.append("deesser")
            chain.append("deesser")
    chain.append(f"equalizer=f={cfg.presence_hz}:t=q:w=2:g={cfg.presence_gain_db}")
    if "acompressor" in filters:
        chain.append(
            f"acompressor=threshold={cfg.compressor_threshold_db}dB:ratio={cfg.compressor_ratio}:attack=8:release=80"
        )
    chain.append("alimiter=limit=0.95")
    return ",".join(chain)


def _profile_polish_chain(profile: StudioSoundProfile, cfg: AudioConfig) -> str:
    if profile.source_mode == "reference":
        return "anull"
    filters = _available_audio_filters()
    chain = [f"highpass=f={max(45, min(cfg.highpass_hz, 65)) if profile.name.startswith('warm_') else cfg.highpass_hz}"]
    if profile.denoise and "afftdn" in filters:
        chain.append("afftdn=nf=-30")
    if cfg.mouth_click_cleanup and "adeclick" in filters:
        chain.extend(["adeclick"] * profile.click_passes)
    if cfg.mouth_click_cleanup and "deesser" in filters:
        chain.extend(["deesser"] * profile.deesser_passes)
    if profile.warm_low_shelf_db:
        chain.append(f"bass=g={profile.warm_low_shelf_db}:f=145:w=0.55")
    if profile.box_cut_db:
        chain.append(f"equalizer=f=900:t=q:w=1.3:g={profile.box_cut_db}")
    if profile.room_cut_db:
        chain.append(f"equalizer=f=3200:t=q:w=1.4:g={profile.room_cut_db}")
    chain.append(f"equalizer=f={cfg.presence_hz}:t=q:w=2:g={profile.presence_gain_db}")
    if "acompressor" in filters:
        chain.append(
            f"acompressor=threshold={cfg.compressor_threshold_db}dB:ratio={profile.compressor_ratio}:attack=8:release=80"
        )
    chain.append("alimiter=limit=0.95")
    return ",".join(chain)


def _spectral_repair_chain(cfg: AudioConfig) -> str:
    filters = _available_audio_filters()
    chain = []
    if "adeclick" in filters and cfg.mouth_click_cleanup:
        chain.append("adeclick")
        chain.append("adeclick")
    if "aclick" in filters and cfg.mouth_click_cleanup:
        chain.append("aclick")
    if "adeclip" in filters:
        chain.append("adeclip")
    if "deesser" in filters and cfg.mouth_click_cleanup:
        chain.append("deesser")
    # Smooth tiny room-tone discontinuities at cut joins without adding fake room tone.
    if "afade" in filters:
        chain.append("afade=t=in:st=0:d=0.015")
    return ",".join(chain)
