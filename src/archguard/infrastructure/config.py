from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from archguard.domain.repository import DEFAULT_EXCLUDED_DIRS, AnalysisOptions


class AnalysisSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    max_file_bytes: int = Field(default=1_048_576, gt=0)
    excluded_dirs: tuple[str, ...] = DEFAULT_EXCLUDED_DIRS
    excluded_patterns: tuple[str, ...] = ("experiments/results", "experiments/results/*")
    source_roots: tuple[str, ...] = ()
    include_hidden: bool = False
    symlink_policy: Literal["skip", "reject"] = "skip"
    fail_fast: bool = False
    strict: bool = False

    def to_domain(self) -> AnalysisOptions:
        return AnalysisOptions(
            self.max_file_bytes,
            self.excluded_dirs,
            self.excluded_patterns,
            self.source_roots,
            self.include_hidden,
            self.symlink_policy,
            self.fail_fast,
        )

    @model_validator(mode="after")
    def valid_policy(self) -> "AnalysisSettings":
        self.to_domain()
        return self


class Settings(BaseSettings):
    """Precedence: environment > .env > explicit/YAML values > defaults."""

    model_config = SettingsConfigDict(
        env_prefix="ARCHGUARD_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="forbid",
        hide_input_in_errors=True,
    )
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_logging: bool = False
    workspace_dir: Path = Path(".")
    experiment_output_dir: Path = Path("experiments/results")
    execution_timeout: float = Field(default=300, gt=0, allow_inf_nan=False)
    random_seed: int = Field(default=0, ge=0)
    repair_provider: str | None = None
    repair_model: str | None = None
    provider_execution_enabled: Literal[False] = False

    @field_validator("repair_provider", "repair_model")
    @classmethod
    def nonempty_optional(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("optional names must not be empty")
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return env_settings, dotenv_settings, init_settings


def read_yaml(path: Path) -> dict[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        raise ValueError("invalid YAML syntax") from None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("configuration must be a mapping with string keys")
    return value


def load_settings(path: Path | None = None) -> Settings:
    values = read_yaml(path) if path else {}
    if any(key not in Settings.model_fields for key in values):
        raise ValueError("configuration contains unknown fields")
    return Settings.model_validate(values)
