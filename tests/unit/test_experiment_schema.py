import json
from pathlib import Path

import pytest

from archguard.infrastructure.config import read_yaml
from archguard.schemas.experiment import ExperimentMetadata

pytestmark = pytest.mark.unit


@pytest.fixture
def metadata(repository_root: Path) -> dict[str, object]:
    return read_yaml(repository_root / "configs/experiments/smoke.yaml")


def test_smoke_and_canonical(metadata: dict[str, object]) -> None:
    model = ExperimentMetadata.model_validate(metadata)
    reordered = ExperimentMetadata.model_validate(dict(reversed(list(metadata.items()))))
    assert model.canonical_json() == reordered.canonical_json()
    assert json.loads(model.canonical_json())["provider_enabled"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "2"),
        ("experiment_name", " "),
        ("benchmark_name", ""),
        ("method_variant", "bogus"),
        ("timeout", 0),
        ("timeout", -1),
        ("timeout", float("inf")),
        ("output_directory", "/tmp/x"),
        ("output_directory", "../x"),
        ("output_directory", "C:/x"),
        ("provider_enabled", True),
        ("repair_model", "model"),
        ("tags", [""]),
        ("surprise", 1),
    ],
)
def test_invalid_metadata(metadata: dict[str, object], field: str, value: object) -> None:
    metadata[field] = value
    with pytest.raises(ValueError):
        ExperimentMetadata.model_validate(metadata)


def test_missing_required(metadata: dict[str, object]) -> None:
    del metadata["experiment_name"]
    with pytest.raises(ValueError):
        ExperimentMetadata.model_validate(metadata)
