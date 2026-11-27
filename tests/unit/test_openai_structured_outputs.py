import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from archguard.domain.canonical import canonical_json
from archguard.domain.v2_execution import frozen_identities
from archguard.domain.v2_patch import REPAIR_RESPONSE_SCHEMA
from archguard.infrastructure.providers.openai_structured_outputs import (
    v2_repair_response_schema,
    validate_openai_structured_outputs_schema,
)
from archguard.infrastructure.v2_evidence import validate_source_free
from archguard.infrastructure.v2_patch_response import StrictRepairResponseExtractor
from archguard.infrastructure.v2_runtime import (
    FakePreparer,
    V2CapabilityProbe,
    V2OpenAIProvider,
)

pytestmark = pytest.mark.unit


def test_repair_schema_is_deterministic_strict_and_complete() -> None:
    first = v2_repair_response_schema()
    second = v2_repair_response_schema()
    assert first is not second
    assert canonical_json(first) == canonical_json(second)
    assert first["type"] == "object"
    assert first["additionalProperties"] is False
    properties = first["properties"]
    required = first["required"]
    assert isinstance(properties, dict)
    assert isinstance(required, list)
    assert set(required) == set(properties)
    assert properties["schema_version"] == {
        "type": "string",
        "enum": [REPAIR_RESPONSE_SCHEMA],
    }
    assert properties["declared_changed_paths"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert properties["rationale_summary"] == {"type": ["string", "null"]}
    assert b'"const"' not in canonical_json(first)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update({"const": "x"}), "unsupported schema keyword"),
        (lambda value: value.update({"allOf": []}), "composition"),
        (lambda value: value.update({"anyOf": []}), "root must be an object"),
        (lambda value: value.pop("additionalProperties"), "bounded properties"),
        (lambda value: value["required"].pop(), "every object property"),
        (lambda value: value.update({"type": "string"}), "root must be an object"),
        (
            lambda value: value["properties"]["task_id"].update({"type": []}),
            "invalid schema type union",
        ),
        (
            lambda value: value["properties"]["task_id"].update({"type": ["string", "string"]}),
            "invalid schema type union",
        ),
        (
            lambda value: value["properties"]["task_id"].update({"type": "date"}),
            "supported explicit type",
        ),
        (
            lambda value: value["properties"]["schema_version"].update({"enum": []}),
            "non-empty list",
        ),
        (
            lambda value: value["properties"]["schema_version"].update({"enum": [1]}),
            "match their declared type",
        ),
        (
            lambda value: value["properties"].update({"task_id": "not-a-schema"}),
            "invalid object property schema",
        ),
        (
            lambda value: value["properties"]["task_id"].update({"properties": {}}),
            "object keywords require object type",
        ),
        (
            lambda value: value["properties"]["declared_changed_paths"].pop("items"),
            "bounded item schema",
        ),
        (
            lambda value: value["properties"]["task_id"].update({"items": {}}),
            "items requires array type",
        ),
        (
            lambda value: (
                value["properties"].update(
                    {"unbounded": {"type": "object", "properties": {}, "required": []}}
                )
                or value["required"].append("unbounded")
            ),
            "bounded properties",
        ),
    ],
)
def test_subset_validator_rejects_incompatible_schemas(mutation, message: str) -> None:  # type: ignore[no-untyped-def]
    schema = copy.deepcopy(v2_repair_response_schema())
    mutation(schema)
    with pytest.raises(ValueError, match=message):
        validate_openai_structured_outputs_schema(schema)


def test_extractor_accepts_only_exact_v2_1_schema_version() -> None:
    response = {
        "schema_version": REPAIR_RESPONSE_SCHEMA,
        "task_id": "schema-test",
        "candidate_id": "candidate-1",
        "unified_diff": (
            "diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n"
            "@@ -1 +1 @@\n-old\n+new\n"
        ),
        "declared_changed_paths": ["demo.py"],
        "rationale_summary": None,
    }
    extractor = StrictRepairResponseExtractor()
    assert extractor.extract(canonical_json(response)).normalized_patch is not None
    response["schema_version"] = "archguard.repair-response/v2.2"
    rejected = extractor.extract(canonical_json(response))
    assert rejected.normalized_patch is None


def test_scientific_and_capability_paths_submit_identical_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Credential:
        configured = True

    schemas: list[object] = []

    class Responses:
        def create(self, **kwargs: object) -> object:
            schemas.append(kwargs["text"]["format"]["schema"])  # type: ignore[index]
            return SimpleNamespace(
                model="gpt-5.4-2026-03-05",
                id="offline-response-id",
                usage=SimpleNamespace(input_tokens=100, output_tokens=10),
                output_text=(
                    '{"schema_version":"archguard.repair-response/v2.1",'
                    '"task_id":"probe","candidate_id":"candidate",'
                    '"unified_diff":"diff --git a/a.py b/a.py\\n--- a/a.py\\n+++ b/a.py\\n'
                    '@@ -1 +1 @@\\n-old\\n+new\\n",'
                    '"declared_changed_paths":["a.py"],"rationale_summary":null}'
                ),
            )

    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for", lambda _: Credential()
    )
    monkeypatch.setattr(
        "archguard.infrastructure.providers.openai_responses.OpenAIResponsesAdapter._client_value",
        lambda self: SimpleNamespace(responses=Responses()),
    )
    V2OpenAIProvider().invoke(FakePreparer("f" * 64).prepare(frozen_identities()[0]))
    result = V2CapabilityProbe().run()
    assert result.scientific_executions == 0
    assert len(schemas) == 2
    assert schemas[0] is not schemas[1]
    assert canonical_json(schemas[0]) == canonical_json(schemas[1])
    assert schemas[0] == v2_repair_response_schema()


def test_historical_schema_probe_record_is_source_free_and_exact(repository_root: Path) -> None:
    path = repository_root / "docs/v2/v2-02a-openai-schema-incident.json"
    value = json.loads(path.read_bytes())
    validate_source_free(value)
    assert value["artifact_zip_sha256"] == (
        "83a41d2011fc5fb522aa8b1b0e1f512bc8f53ac5a5592a717efb4e31f88d5f11"
    )
    assert value["evidence_json_sha256"] == (
        "d348ed7c775c25a2ea2283842a5c80913e3f06890e7aa11bc3eacd8d4bbe83d2"
    )
    assert value["status"] == "PROVIDER_REJECTED"
    assert value["provider_request_attempts"] == 1
    assert value["accepted_provider_calls"] == value["scientific_executions"] == 0
    assert value["diagnostic"] == {
        "fingerprint": "4454817226b88eff7d182b9c2a0b801aff29b9e11de726ea85573dab9f4ea8b0",
        "http_status": 400,
        "kind": "INVALID_REQUEST",
        "provider_code": "invalid_json_schema",
        "request_id_hash": ("87663d44e9847c002f6ccb53fec14e88b14af36a45c3ce3dc86a3f6d78ce462e"),
        "retryable": False,
        "stage": "request",
        "usage_returned": False,
    }
    assert not list(path.parent.glob("*.zip"))
