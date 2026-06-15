"""eddy.toml load/merge/validate. Doctor writes hardware-derived sections only."""

from __future__ import annotations

import os
from pathlib import Path

import tomlkit
from pydantic import BaseModel, Field

CONFIG_ENV = "EDDY_CONFIG"
DEFAULT_USER_CONFIG = Path("~/.config/eddy/eddy.toml").expanduser()
PROJECT_CONFIG = Path("eddy.toml")


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen36-27b-codex:q4"
    judge_model: str = ""  # empty -> use model
    temperature: float = 0.3
    max_tokens: int = 4096
    num_ctx: int = 32768


class AnthropicConfig(BaseModel):
    enabled: bool = False
    model: str = "claude-haiku-4-5-20251001"
    api_key_env: str = "ANTHROPIC_API_KEY"
    temperature: float = 0.3
    max_tokens: int = 4096


class OpenAIConfig(BaseModel):
    enabled: bool = False
    model: str = "gpt-5.1-mini"
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = ""  # set for Azure / a proxy / a self-hosted OpenAI-compatible endpoint
    temperature: float = 0.3
    max_tokens: int = 4096


class CliProviderConfig(BaseModel):
    enabled: bool = False
    binary: str = ""  # "codex" or "claude"
    model: str = ""  # optional model override flag


class ProviderConfig(BaseModel):
    active: str = "ollama"
    # which brain runs the editorial-reasoning passes (beat map, cut decisions, revisions,
    # judge). "auto" = prefer a stronger brain (claude_cli > anthropic) when available, else
    # fall back to `active`. "local" pins it to `active`. Or name a provider explicitly.
    editorial: str = "auto"
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    codex_cli: CliProviderConfig = Field(default_factory=lambda: CliProviderConfig(binary="codex"))
    claude_cli: CliProviderConfig = Field(default_factory=lambda: CliProviderConfig(binary="claude"))


class TranscribeConfig(BaseModel):
    engine: str = "faster-whisper"
    model: str = "large-v3"
    compute_type: str = "int8"
    language: str = ""  # "" = auto-detect; set to "en"/"es"/... or pass --language to force
    vocab_prompt: str = ""  # optional domain vocabulary to bias transcription (was a hardcoded personal list)


class LoopConfig(BaseModel):
    max_iterations: int = 15  # v0.3: raised from 5; plateau is the real brake
    judge_threshold: float = 8.0
    plateau_rounds: int = 2  # v0.3: stop after K rounds with no best-quality gain
    length_ceiling_minutes: float = 14.0  # v0.3: length guardrail (constraint, not a target)
    quality_weight_objective: float = 0.6  # v0.3: hybrid quality = 0.6*objective + 0.4*critic
    quality_weight_critic: float = 0.4
    ship_panel: bool = True  # v0.3: 3-lens majority panel at final ship
    ship_panel_size: int = 3
    max_model_calls_per_iteration: int = 4
    # v0.4 runaway guard, enforced at the iteration head: a pathological source on a cloud brain
    # could otherwise run up to max_iterations full-render rounds for hours at unbounded cost.
    # max_total_model_calls is CUMULATIVE across --resume (counted from receipts, a safe over-count
    # since judge retries log extra lines); max_wall_clock_minutes is PER-PROCESS (resets on resume).
    # Generous defaults — these catch true runaways, not legitimate long runs.
    max_total_model_calls: int = 60
    max_wall_clock_minutes: float = 120.0
    max_run_cost_usd: float = 0.0  # cumulative paid-API spend cap; 0 = unlimited (local/subscription = free)
    # v0.3: duration_band / default_target_minutes are advisory only — the loop now
    # maximizes quality with length as a ceiling constraint, not a target band.
    duration_band: tuple[float, float] = (0.8, 1.2)  # x target (advisory)
    default_target_minutes: float = 12.0  # advisory initial-cut preference
    # v0.3.1 speed-to-fit: deterministic time-compression of draggy beats to close a residual
    # gap to the ceiling that cutting alone can't. Off by default until proven on a dogfood.
    enable_speed_ramp: bool = False
    speed_ramp_max_multiplier: float = 1.4   # hard cap; atempo preserves pitch, but >~1.5 sounds rushed
    speed_ramp_min_beat_s: float = 15.0      # don't bother speeding beats shorter than this
    speed_ramp_max_wpm: float = 160.0        # only speed SLOW, long beats (fast beats are already paced)
    # v0.3.2 aggressive cut (default path): keep the loop cutting toward the ceiling instead of
    # plateau-quitting on a length-blind quality metric. Length is a SECOND convergence axis here —
    # it gates the plateau but is never folded into quality_score (that reward-hacked in v0.3).
    ceiling_tolerance_s: float = 5.0       # within this many seconds of the ceiling counts as "reached"
    min_length_progress_s: float = 5.0     # a round must cut at least this much closer to count as progress
    protection_budget_frac: float = 0.20   # model-declared protected_moments trimmed to <= this * source_s
    # v0.3.2 deterministic trim-to-fit backstop (off by default; mirrors the speed-ramp posture)
    enable_aggressive_trim: bool = False
    trim_judge_tolerance: float = 0.5      # adopt a trim only if judge >= pre-trim baseline - this


class RenderConfig(BaseModel):
    proxy_height: int = 480
    proxy_preset: str = "ultrafast"
    final_crf: int = 18
    cut_pad_before_ms: int = 120
    cut_pad_after_ms: int = 160
    boundary_fade_ms: int = 30


class ShortsConfig(BaseModel):
    count: int = 3
    min_s: float = 20.0
    max_s: float = 59.0


class AudioConfig(BaseModel):
    """Local 'studio sound' — denoise/dereverb + speech EQ + loudness normalization."""
    studio_sound: bool = True
    deep_filter_binary: str = "deep-filter"  # DeepFilterNet CLI if present; else ffmpeg-only
    target_lufs: float = -14.0  # YouTube integrated loudness
    true_peak_db: float = -1.5
    lra: float = 11.0
    highpass_hz: int = 80
    presence_hz: int = 3500  # gentle speech-presence lift
    presence_gain_db: float = 2.0


class ThumbnailsConfig(BaseModel):
    enabled: bool = True
    gemini_model: str = "gemini-3.1-flash-image-preview"
    gemini_key_env: str = "GEMINI_API_KEY"
    openai_key_env: str = "OPENAI_API_KEY"
    candidates_per_provider: int = 2


class GatesConfig(BaseModel):
    max_dead_air_s: float = 1.5
    min_range_s: float = 1.2
    max_av_drift_s: float = 0.5
    min_boundary_handle_s: float = 0.10
    # audio-truth silence handling (kills "mouth moving, no sound")
    silence_noise_db: float = -34.0  # silencedetect noise floor
    silence_min_cut_s: float = 0.40  # audio-silent span >= this (and no words) gets removed
    silence_handle_s: float = 0.10  # silence left each side of a removed silent span
    max_output_silence_s: float = 0.6  # output gate: non-protected silence above this fails


class PathsConfig(BaseModel):
    runs_dir: str = "~/.eddy/runs"  # lowercase/hidden: avoids the ~/Eddy vs ~/eddy case collision


CONFIG_SCHEMA_VERSION = 1


class EddyConfig(BaseModel):
    schema_version: int = CONFIG_SCHEMA_VERSION  # stamped so an old config can be migrated forward
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    shorts: ShortsConfig = Field(default_factory=ShortsConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    thumbnails: ThumbnailsConfig = Field(default_factory=ThumbnailsConfig)
    gates: GatesConfig = Field(default_factory=GatesConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @property
    def runs_dir(self) -> Path:
        return Path(self.paths.runs_dir).expanduser()


def config_path() -> Path:
    """Resolution order: $EDDY_CONFIG > ./eddy.toml > ~/.config/eddy/eddy.toml."""
    if env := os.environ.get(CONFIG_ENV):
        return Path(env).expanduser()
    if PROJECT_CONFIG.exists():
        return PROJECT_CONFIG
    return DEFAULT_USER_CONFIG


def migrate_config(data: dict) -> dict:
    """Forward-migrate an older config dict so a newer Eddy reads an older file (renames/moves go
    here instead of hard-rejecting). v1 is the baseline; this stamps a missing schema_version."""
    data = dict(data)
    data.setdefault("schema_version", 1)
    # future: if data["schema_version"] < N: rename/relocate fields, then bump
    return data


def load_config(path: Path | None = None) -> EddyConfig:
    p = path or config_path()
    if not p.exists():
        return EddyConfig()
    try:
        doc = tomlkit.parse(p.read_text())
        return EddyConfig.model_validate(migrate_config(doc.unwrap()))
    except Exception as e:
        # a malformed / out-of-date config must NOT brick every command (including doctor). Warn and
        # fall back to defaults; `eddy doctor` can rewrite a clean config.
        import sys

        print(
            f"[eddy] WARNING: could not load config at {p} ({type(e).__name__}); using defaults. "
            "Run `eddy doctor` to rewrite it.",
            file=sys.stderr,
        )
        return EddyConfig()


def update_config_sections(sections: dict, path: Path | None = None) -> Path:
    """Merge `sections` into the TOML doc, preserving comments/user keys (doctor's writer)."""
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.parse(p.read_text()) if p.exists() else tomlkit.document()

    def merge(target, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict):
                if k not in target:
                    target[k] = tomlkit.table()
                merge(target[k], v)
            else:
                target[k] = v

    merge(doc, sections)
    EddyConfig.model_validate(doc.unwrap())  # refuse to write invalid config
    p.write_text(tomlkit.dumps(doc))
    return p
