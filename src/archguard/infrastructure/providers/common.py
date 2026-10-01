"""Shared structured response conversion."""

import hashlib
import json
from dataclasses import asdict
from typing import Any

from pydantic import TypeAdapter, ValidationError

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import AgentRequest, AgentResponse, validate_response
from archguard.domain.providers import ProviderErrorCategory, ProviderFailure
from archguard.infrastructure.providers.retry import ProviderInvocationError


def response_schema() -> dict[str, Any]:
    schema = TypeAdapter(AgentResponse).json_schema()
    result = _strict(schema)
    if not isinstance(result, dict):
        raise TypeError("response schema must be an object")
    return result


def _strict(value: Any) -> Any:
    if isinstance(value, dict):
        result = {key: _strict(item) for key, item in value.items()}
        if result.get("type") == "object":
            result["additionalProperties"] = False
        return result
    if isinstance(value, list):
        return [_strict(item) for item in value]
    return value


def parse_response(provider: str, request: AgentRequest, payload: object) -> AgentResponse:
    try:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        response = TypeAdapter(AgentResponse).validate_json(raw, strict=True)
        validate_response(request, response)
        return response
    except (TypeError, ValueError, ValidationError):
        raise ProviderInvocationError(
            ProviderFailure(
                ProviderErrorCategory.MALFORMED_OUTPUT,
                False,
                "Provider returned invalid structured output.",
                provider,
                "response_validation",
            )
        ) from None


def response_fingerprint(response: AgentResponse) -> str:
    return hashlib.sha256(canonical_json(asdict(response))).hexdigest()


def value(item: object, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)
