"""OpenAI Responses API adapter using only the documented public response shape."""

import json
from typing import Any, Protocol, cast

from archguard.application.services.prompts import construct_prompt
from archguard.domain.orchestration import AgentRequest, AgentResponse
from archguard.domain.providers import (
    ProviderCapabilities,
    ProviderCapability,
    ProviderErrorCategory,
    ProviderFailure,
    ProviderUsage,
)
from archguard.infrastructure.providers.common import parse_response, response_schema, value
from archguard.infrastructure.providers.configuration import ProviderSettings
from archguard.infrastructure.providers.credentials import ProviderCredential
from archguard.infrastructure.providers.retry import ProviderInvocationError


class ResponsesResource(Protocol):
    def create(self, **kwargs: Any) -> object: ...


class OpenAIClient(Protocol):
    responses: ResponsesResource


CAPABILITIES = ProviderCapabilities(
    "openai",
    frozenset(
        {
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.STRICT_JSON_SCHEMA,
            ProviderCapability.CONFIGURABLE_REASONING,
            ProviderCapability.USAGE_REPORTING,
            ProviderCapability.STREAMING,
            ProviderCapability.REQUEST_CANCELLATION,
            ProviderCapability.STATELESS_OPERATION,
            ProviderCapability.PROMPT_CACHING,
            ProviderCapability.REQUEST_ID,
            ProviderCapability.SERVER_DATA_CONTROLS,
        }
    ),
)


class OpenAIResponsesAdapter:
    def __init__(
        self,
        settings: ProviderSettings,
        credential: ProviderCredential,
        client: OpenAIClient | None = None,
    ) -> None:
        if settings.provider != "openai":
            raise ValueError("provider configuration mismatch")
        self.settings = settings
        self.credential = credential
        self._client = client
        self.last_usage: ProviderUsage | None = None
        self.last_model: str | None = None
        self.last_request_id: str | None = None

    def capabilities(self) -> ProviderCapabilities:
        return CAPABILITIES

    def _client_value(self) -> OpenAIClient:
        if self._client is None:
            from openai import OpenAI

            self._client = cast(
                OpenAIClient,
                OpenAI(
                    api_key=self.credential.reveal_for_client(),
                    max_retries=0,
                    timeout=self.settings.request_timeout_seconds,
                ),
            )
        return self._client

    def invoke(self, request: AgentRequest) -> AgentResponse:
        prompt = construct_prompt(request)
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "input": [{"role": "developer", "content": prompt.text}],
            "max_output_tokens": self.settings.maximum_output_units,
            "store": not self.settings.stateless,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "agent_response",
                    "strict": True,
                    "schema": response_schema(),
                }
            },
            "tools": [],
        }
        if self.settings.temperature is not None:
            kwargs["temperature"] = self.settings.temperature
        if self.settings.reasoning_effort is not None:
            kwargs["reasoning"] = {"effort": self.settings.reasoning_effort}
        try:
            response = self._client_value().responses.create(**kwargs)
        except ProviderInvocationError:
            raise
        except Exception as error:
            raise self._map_error(error) from None
        self.last_model = str(value(response, "model", ""))
        self.last_request_id = str(value(response, "id", "")) or None
        usage = value(response, "usage")
        self.last_usage = ProviderUsage(
            int(value(usage, "input_tokens", 0)),
            int(value(usage, "output_tokens", 0)),
            value(value(usage, "input_tokens_details", {}), "cached_tokens"),
            value(value(usage, "output_tokens_details", {}), "reasoning_tokens"),
            "openai",
            self.last_model,
        )
        status = value(response, "status")
        if status == "incomplete":
            reason = value(value(response, "incomplete_details", {}), "reason")
            category = (
                ProviderErrorCategory.OUTPUT_LIMIT
                if reason in {"max_output_tokens", "max_tokens"}
                else ProviderErrorCategory.INCOMPLETE
            )
            raise ProviderInvocationError(
                ProviderFailure(
                    category,
                    False,
                    "Provider response was incomplete.",
                    "openai",
                    "response",
                    request_id=self.last_request_id,
                )
            )
        texts: list[str] = []
        for item in value(response, "output", ()) or ():
            if value(item, "type") != "message":
                continue
            for content in value(item, "content", ()) or ():
                if value(content, "type") == "refusal":
                    raise ProviderInvocationError(
                        ProviderFailure(
                            ProviderErrorCategory.REFUSAL,
                            False,
                            "Provider refused the request.",
                            "openai",
                            "response",
                            request_id=self.last_request_id,
                        )
                    )
                if value(content, "type") == "output_text":
                    texts.append(str(value(content, "text", "")))
        if not texts:
            raise ProviderInvocationError(
                ProviderFailure(
                    ProviderErrorCategory.INCOMPLETE,
                    False,
                    "Provider returned no structured output.",
                    "openai",
                    "response",
                    request_id=self.last_request_id,
                )
            )
        try:
            payload = json.loads("".join(texts))
        except json.JSONDecodeError:
            payload = None
        return parse_response("openai", request, payload)

    def _map_error(self, error: Exception) -> ProviderInvocationError:
        status = getattr(error, "status_code", None)
        mapping = {
            401: ProviderErrorCategory.AUTHENTICATION,
            403: ProviderErrorCategory.PERMISSION,
            408: ProviderErrorCategory.TIMEOUT,
            429: ProviderErrorCategory.RATE_LIMITED,
            500: ProviderErrorCategory.UNAVAILABLE,
            502: ProviderErrorCategory.UNAVAILABLE,
            503: ProviderErrorCategory.OVERLOADED,
            504: ProviderErrorCategory.TIMEOUT,
        }
        category = mapping.get(
            status if isinstance(status, int) else -1,
            ProviderErrorCategory.NETWORK
            if isinstance(error, (ConnectionError, TimeoutError))
            else ProviderErrorCategory.INVALID_REQUEST
            if status == 400
            else ProviderErrorCategory.INTERNAL,
        )
        retryable = category in {
            ProviderErrorCategory.RATE_LIMITED,
            ProviderErrorCategory.OVERLOADED,
            ProviderErrorCategory.UNAVAILABLE,
            ProviderErrorCategory.NETWORK,
            ProviderErrorCategory.TIMEOUT,
        }
        return ProviderInvocationError(
            ProviderFailure(
                category, retryable, "OpenAI request failed safely.", "openai", "request"
            )
        )
