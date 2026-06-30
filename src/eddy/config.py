"""eddy.toml load/merge/validate. Doctor writes hardware-derived sections only."""

from __future__ import annotations

import os
from pathlib import Path

import tomlkit
from pydantic import BaseModel, Field

CONFIG_ENV = "EDDY_CONFIG"
MOTION_MODE_ENV = "EDDY_MOTION_MODE"
AUDIO_AUDITION_ENV = "EDDY_AUDIO_AUDITION"
DEFAULT_USER_CONFIG = Path("~/.config/eddy/eddy.toml").expanduser()
PROJECT_CONFIG = Path("eddy.toml")


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen36-27b-codex:q4"
    judge_model: str = ""  # empty -> use model
    temperature: float = 0.3
    max_tokens: int = 4096
    num_ctx: int = 32768
    # v1.6: opt-in adaptive context. When >num_ctx, a large prompt grows num_ctx toward this cap so a
    # long transcript's input + num_predict both fit. DEFAULT OFF (0): a v1.6 live run showed that
    # bumping the local 27B model to a 49152 window made editorial calls 7-16x slower (a 50-min revise),
    # for a truncation risk the string-aware JSON salvage in extract_json already covers. Set >32768
    # only with a fast/large-VRAM backend. 0 = keep num_ctx fixed.
    num_ctx_max: int = 0
    seed: int | None = None  # set (with temperature=0) for EXACT reproducible editorial output


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
    # exit codes a local CLI/wrapper uses to mean "transient, re-run" (e.g. a one-time auth/pairing
    # settle). Empty by default — generic; users with such a wrapper configure their own codes.
    transient_exit_codes: list[int] = Field(default_factory=list)


class ProviderConfig(BaseModel):
    active: str = "ollama"
    # which brain runs the editorial-reasoning passes (beat map, cut decisions, revisions,
    # judge). "auto" = prefer Codex/Claude/API when available, else fall back to `active`.
    # "local" pins it to `active`. Or name a provider explicitly.
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
    max_iterations: int = 50  # unattended editor: keep repairing much longer before declaring a blocker
    require_gate_pass: bool = True  # never ship known QA failures as "done"
    identical_failure_limit: int = 3  # repeated same failure signature => impossible blocker, not more thrash
    judge_threshold: float = 8.0
    plateau_rounds: int = 2  # v0.3: stop after K rounds with no best-quality gain
    length_ceiling_minutes: float = 14.0  # v0.3: length guardrail (constraint, not a target)
    quality_weight_objective: float = 0.6  # v0.3: hybrid quality = 0.6*objective + 0.4*critic
    quality_weight_critic: float = 0.4
    ship_panel: bool = True  # v0.3: 3-lens majority panel at final ship
    ship_panel_size: int = 3
    # v1.7 best-of-N self-consistency for the iteration-1 EXTRACT draft. The local 27B brain is
    # wildly non-deterministic (v1.7 baseline: blocks 6→151, dur 26s→45min on one source) and ~45% of
    # single draws are over-ceiling catastrophes; sampling N drafts and picking the best by a
    # deterministic render-free selector cut judge stdev 1.154→0.339 (↓71%) and eliminated catastrophes
    # on a full 5-draw confirmation. Default 5 = the PROVEN setting (0.45^5≈2% all-bad-group rate; N=3
    # was too small). 1 = OFF (single draft, pre-v1.7). Gated to extract mode in the loop, so
    # normal/steer edits are unaffected regardless of this value (they always take the single-draft path).
    ensemble_n: int = 5
    # v1.7.5: a residual variance source the v1.7 confirmation flagged as future work — a "bad
    # group" where every one of the N draws is a catastrophe (none compile feasibly close to the
    # ceiling). Best-of-N over a uniformly bad group still ships the least-bad catastrophe; redraw
    # up to this many extra N-sized batches when the surviving best is still >2x the ceiling over,
    # so a single unlucky group gets a second/third roll instead of being accepted outright. 0 =
    # off (pre-v1.7.5 behavior: ship whatever best-of-N produced, no redraw).
    ensemble_retry_max: int = 2
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
    # Practical spoken-word handles. Whisper word starts are approximate; dogfood proved tiny
    # 40/60ms pads can shave first syllables even when text-level gates are green.
    cut_pad_before_ms: int = 160
    cut_pad_after_ms: int = 220
    # Numbers and metrics are high-cost mistakes: "104 clicks" must never become "100 clicks".
    # These wider handles apply only when an edit boundary touches a number/metric phrase.
    numeric_pad_before_ms: int = 220
    numeric_pad_after_ms: int = 320
    boundary_fade_ms: int = 30
    long_camera_size: int = 260
    long_camera_radius: int = 30
    long_camera_margin: int = 0


class ShortsConfig(BaseModel):
    count: int = 5
    min_s: float = 10.0
    max_s: float = 59.0
    max_silent_motion_s: float = 1.2
    require_hook_playbook: bool = True
    hook_playbook_min_records: int = 1000
    hook_playbook_path: str = "docs/references/short-form-hook-playbook.jsonl"


class AudioConfig(BaseModel):
    """Local 'studio sound' — speech enhancement, denoise/dereverb, click repair, loudness."""
    studio_sound: bool = True
    require_heavy_backend: bool = True
    # `auto` renders multiple candidates and chooses the least overprocessed voice that still
    # reduces clicks. This prevents the classic failure mode: clicks are gone, but the voice
    # sounds hollow/echoey because every cleanup filter was stacked at max intensity.
    studio_sound_profile: str = "auto"
    studio_sound_candidate_profiles: list[str] = Field(
        default_factory=lambda: [
            "source_reference",
            "warm_room_tame",
            "warm_deep_tame",
            "warm_click_tame",
            "warm_model_10",
            "natural_voice",
            "click_rescue",
            "broadcast_clean",
            "surgical_click_rescue",
        ]
    )
    studio_sound_env: str = "~/.cache/eddy/studio-sound/resemble-enhance-py311"
    heavy_model_device: str = "auto"  # auto | cuda | mps | cpu
    deep_filter_binary: str = "deepFilter"  # DeepFilterNet CLI if present; else blocked/ffmpeg fallback
    heavy_backend_stall_timeout_s: int = 300
    # Ordered heavy-model backends. Eddy attempts these before ffmpeg-only polish when installed.
    heavy_model_preference: list[str] = Field(
        default_factory=lambda: ["deepfilternet", "resemble-enhance"]
    )
    write_ab_samples: bool = True
    click_threshold: float = 0.68
    mouth_click_score_max: float = 0.045
    target_lufs: float = -14.0  # YouTube integrated loudness
    true_peak_db: float = -1.5
    lra: float = 11.0
    highpass_hz: int = 80
    presence_hz: int = 3500  # gentle speech-presence lift
    presence_gain_db: float = 2.5
    mouth_click_cleanup: bool = True
    compressor_threshold_db: float = -20.0
    compressor_ratio: float = 3.0
    echo_artifact_max_score: float = 0.42
    require_echo_artifact_gate: bool = True


class ThumbnailsConfig(BaseModel):
    enabled: bool = True
    # thumbnails upload a real FACE frame to a cloud image model — opt-in, not automatic. Off by
    # default so a person's likeness is never sent without explicit consent.
    consent_to_upload: bool = False
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
    silence_handle_s: float = 0.12  # silence left each side of a removed silent span
    max_output_silence_s: float = 0.6  # output gate: non-protected silence above this fails
    gap_pacing_min_s: float = 0.35  # ordinary spoken-word gaps should keep a natural floor
    gap_pacing_max_s: float = 0.55  # unprotected spoken-word gaps above this feel draggy
    allow_redaction: bool = False  # default is no blur/redaction; use explicit opt-in for privacy edits
    # v1.6 extract continuity (only applied when compile_edl runs with extract=True): consolidate the
    # many small keep ranges a topical extract produces into a few contiguous blocks, so explanations
    # aren't severed mid-thought. A normal/steer edit never enters this path.
    extract_bridge_gap_s: float = 6.0          # bridge consecutive keep blocks separated by <= this
    extract_min_block_s: float = 2.5           # drop an isolated keep block shorter than this (sliver)
    extract_phrase_snap_window_s: float = 1.5  # snap a block edge OUT to a phrase boundary within this


class TelemetryConfig(BaseModel):
    enabled: bool = False  # OPT-IN only — never on by default
    endpoint: str = ""     # where anonymized failure beacons are sent (you provide this)


class MotionConfig(BaseModel):
    """HyperFrames-backed first-60 motion layer for default YouTube edits."""

    mode: str = "required"  # required | off
    first_60_seconds: float = 60.0
    cache_dir: str = ".eddy/hyperframes-cache"


class PathsConfig(BaseModel):
    runs_dir: str = "~/.eddy/runs"  # lowercase/hidden: avoids the ~/Eddy vs ~/eddy case collision


class RunProfile(BaseModel):
    """Named per-channel run defaults (e.g. one profile per YouTube channel). Only the fields you set
    take effect; an explicit CLI flag on `eddy run` always overrides the profile."""
    target_minutes: float | None = None
    format: str | None = None         # tutorial|lesson|longform|podcast|default — maps to a ceiling
    language: str | None = None       # force a transcription language for this channel
    skip_shorts: bool | None = None
    skip_package: bool | None = None
    focus: str | None = None          # default focus brief for this channel (e.g. a recurring topic)


CONFIG_SCHEMA_VERSION = 1


class EddyConfig(BaseModel):
    schema_version: int = CONFIG_SCHEMA_VERSION  # stamped so an old config can be migrated forward
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    shorts: ShortsConfig = Field(default_factory=ShortsConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    motion: MotionConfig = Field(default_factory=MotionConfig)
    thumbnails: ThumbnailsConfig = Field(default_factory=ThumbnailsConfig)
    gates: GatesConfig = Field(default_factory=GatesConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    profiles: dict[str, RunProfile] = Field(default_factory=dict)  # named per-channel run defaults

    @property
    def runs_dir(self) -> Path:
        return Path(self.paths.runs_dir).expanduser()


def resolve_profile(cfg: "EddyConfig", name: str | None) -> RunProfile:
    """Look up a named run profile. None/empty -> an all-None profile (no overrides). An unknown
    name is a hard error so a typo'd channel doesn't silently run with wrong defaults."""
    if not name:
        return RunProfile()
    try:
        return cfg.profiles[name]
    except KeyError:
        known = ", ".join(sorted(cfg.profiles)) or "(none configured)"
        raise KeyError(f"unknown profile {name!r}; configured profiles: {known}") from None


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
        return _apply_env_overrides(EddyConfig())
    try:
        doc = tomlkit.parse(p.read_text())
        cfg = EddyConfig.model_validate(migrate_config(doc.unwrap()))
        return _apply_env_overrides(cfg)
    except Exception as e:
        # a malformed / out-of-date config must NOT brick every command (including doctor). Warn and
        # fall back to defaults; `eddy doctor` can rewrite a clean config.
        import sys

        print(
            f"[eddy] WARNING: could not load config at {p} ({type(e).__name__}); using defaults. "
            "Run `eddy doctor` to rewrite it.",
            file=sys.stderr,
        )
        return _apply_env_overrides(EddyConfig())


def _apply_env_overrides(cfg: EddyConfig) -> EddyConfig:
    motion_mode = os.environ.get(MOTION_MODE_ENV)
    if motion_mode:
        cfg.motion.mode = motion_mode.strip().lower()
    audio_audition = os.environ.get(AUDIO_AUDITION_ENV)
    if audio_audition:
        cfg.audio.studio_sound = audio_audition.strip().lower() != "off"
    return cfg


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
