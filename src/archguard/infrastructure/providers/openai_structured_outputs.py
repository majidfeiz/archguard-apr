"""Deterministic schemas for the OpenAI strict Structured Outputs subset."""

from __future__ import annotations

from typing import cast

from archguard.domain.v2_patch import REPAIR_RESPONSE_SCHEMA

type JsonSchema = dict[str, object]

_ALLOWED_KEYWORDS = frozenset(
    {"type", "enum", "properties", "required", "additionalProperties", "items"}
)
_COMPOSITION_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "not"})


def v2_repair_response_schema() -> JsonSchema:
    """Build the strict provider schema for the provider-neutral V2.1 contract."""
    schema: JsonSchema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string", "enum": [REPAIR_RESPONSE_SCHEMA]},
            "task_id": {"type": "string"},
            "candidate_id": {"type": "string"},
            "unified_diff": {"type": "string"},
            "declared_changed_paths": {
                "type": "array",
                "items": {"type": "string"},
            },
            "rationale_summary": {"type": ["string", "null"]},
        },
        "required": [
            "schema_version",
            "task_id",
            "candidate_id",
            "unified_diff",
            "declared_changed_paths",
            "rationale_summary",
        ],
    }
    validate_openai_structured_outputs_schema(schema)
    return schema


def validate_openai_structured_outputs_schema(schema: JsonSchema) -> None:
    """Reject schema constructs outside ArchGuard's strict OpenAI subset."""
    if schema.get("type") != "object" or "anyOf" in schema:
        raise ValueError("Structured Outputs root must be an object without anyOf")
    _validate_node(schema, root=True)


def _validate_node(node: JsonSchema, *, root: bool = False) -> None:
    keywords = set(node)
    unsupported = keywords - _ALLOWED_KEYWORDS
    if unsupported:
        if unsupported & _COMPOSITION_KEYWORDS:
            raise ValueError("unsupported schema composition keyword")
        raise ValueError("unsupported schema keyword")

    node_type = node.get("type")
    allowed_types = {"string", "object", "array", "null", "number", "integer", "boolean"}
    if isinstance(node_type, list):
        if not node_type or len(node_type) != len(set(node_type)):
            raise ValueError("invalid schema type union")
        if any(not isinstance(item, str) or item not in allowed_types for item in node_type):
            raise ValueError("unsupported schema type")
    elif not isinstance(node_type, str) or node_type not in allowed_types:
        raise ValueError("schema nodes require a supported explicit type")
    if root and node_type != "object":
        raise ValueError("Structured Outputs root must be an object")

    if "enum" in node:
        values = node["enum"]
        if not isinstance(values, list) or not values:
            raise ValueError("enum must be a non-empty list")
        if node_type == "string" and any(not isinstance(item, str) for item in values):
            raise ValueError("enum values must match their declared type")

    if node_type == "object":
        properties = node.get("properties")
        required = node.get("required")
        if (
            node.get("additionalProperties") is not False
            or not isinstance(properties, dict)
            or not isinstance(required, list)
        ):
            raise ValueError("objects require bounded properties and additionalProperties=false")
        if set(required) != set(properties) or len(required) != len(properties):
            raise ValueError("every object property must be required exactly once")
        for name, child in properties.items():
            if not isinstance(name, str) or not isinstance(child, dict):
                raise ValueError("invalid object property schema")
            _validate_node(cast(JsonSchema, child))
    elif any(key in node for key in ("properties", "required", "additionalProperties")):
        raise ValueError("object keywords require object type")

    if node_type == "array":
        items = node.get("items")
        if not isinstance(items, dict):
            raise ValueError("arrays require a bounded item schema")
        _validate_node(cast(JsonSchema, items))
    elif "items" in node:
        raise ValueError("items requires array type")
