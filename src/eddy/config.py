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
    language: str = "en"


class LoopConfig(BaseModel):
    max_iterations: int = 5
    judge_threshold: float = 8.0
    max_model_calls_per_iteration: int = 4
    duration_band: tuple[float, float] = (0.8, 1.2)  # x target
    default_target_minutes: float = 12.0


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
    runs_dir: str = "~/Eddy/runs"


class EddyConfig(BaseModel):
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    shorts: ShortsConfig = Field(default_factory=ShortsConfig)
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


def load_config(path: Path | None = None) -> EddyConfig:
    p = path or config_path()
    if not p.exists():
        return EddyConfig()
    doc = tomlkit.parse(p.read_text())
    return EddyConfig.model_validate(doc.unwrap())


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
