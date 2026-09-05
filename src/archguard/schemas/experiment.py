import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from archguard.domain.models import identifier, relative_path


class ExperimentMetadata(BaseModel):
    """Metadata only; validation authorizes no execution."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["1"]
    experiment_name: str
    benchmark_name: str
    method_variant: Literal[
        "foundation_smoke",
        "single_agent",
        "architecture_aware",
        "graph_retrieval",
        "multi_agent",
        "full",
    ]
    seed: int = Field(ge=0)
    timeout: float = Field(gt=0, allow_inf_nan=False)
    output_directory: str
    provider_enabled: Literal[False] = False
    repair_provider: None = None
    repair_model: None = None
    tags: tuple[str, ...] = ()
    description: str

    @field_validator("experiment_name", "benchmark_name", "description")
    @classmethod
    def valid_identifier(cls, value: str) -> str:
        return identifier(value)

    @field_validator("output_directory")
    @classmethod
    def valid_path(cls, value: str) -> str:
        return relative_path(value)

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(identifier(tag) for tag in value)

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
