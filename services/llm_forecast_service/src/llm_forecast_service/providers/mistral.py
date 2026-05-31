from __future__ import annotations

import asyncio
import json
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import ValidationError

from llm_forecast_service.errors import ServiceError
from llm_forecast_service.schemas import (
    ForecastAdjustmentOutput,
    ForecastAdjustmentRequest,
)
from llm_forecast_service.settings import ServiceSettings

MISTRAL_CHAT_COMPLETIONS_URL = "https://api.mistral.ai/v1/chat/completions"

_FORECAST_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "forecast_points": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer"},
                    "value": {"type": "number"},
                },
                "required": ["year", "value"],
                "additionalProperties": False,
            },
        },
        "rationale": {"type": "string", "maxLength": 2000},
        "assumptions": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 500},
        },
        "warnings": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 500},
        },
    },
    "required": ["forecast_points", "rationale", "assumptions", "warnings"],
    "additionalProperties": False,
}


class MistralProvider:
    provider_name = "mistral"

    def __init__(
        self,
        settings: ServiceSettings,
        *,
        api_url: str = MISTRAL_CHAT_COMPLETIONS_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._api_url = api_url
        self._transport = transport

    @property
    def model_name(self) -> str:
        return self._settings.mistral_model

    async def generate_adjustment(
        self,
        request: ForecastAdjustmentRequest,
    ) -> ForecastAdjustmentOutput:
        response_payload = await self._call_mistral(request)
        content = _extract_message_content(response_payload)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ServiceError(
                "invalid_provider_response",
                "Mistral returned invalid JSON.",
                status_code=502,
                details={"provider": "mistral"},
            ) from exc
        if not isinstance(parsed, dict):
            raise ServiceError(
                "invalid_provider_response",
                "Mistral response JSON must be an object.",
                status_code=502,
                details={"provider": "mistral"},
            )
        try:
            return ForecastAdjustmentOutput.model_validate(parsed)
        except ValidationError as exc:
            raise ServiceError(
                "invalid_provider_response",
                "Mistral response did not match the forecast schema.",
                status_code=502,
                details={"provider": "mistral", "errors": exc.errors()},
            ) from exc

    async def _call_mistral(self, request: ForecastAdjustmentRequest) -> dict[str, Any]:
        payload = _build_mistral_payload(request, self._settings)
        headers = {
            "Authorization": f"Bearer {self._settings.mistral_api_key}",
            "Content-Type": "application/json",
        }
        attempts = max(0, self._settings.max_retries) + 1
        timeout = httpx.Timeout(self._settings.timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout, transport=self._transport
        ) as client:
            for attempt_index in range(attempts):
                try:
                    response = await client.post(
                        self._api_url, headers=headers, json=payload
                    )
                except httpx.TimeoutException as exc:
                    if attempt_index < attempts - 1:
                        await _retry_sleep(attempt_index)
                        continue
                    raise ServiceError(
                        "provider_timeout",
                        "Mistral request timed out.",
                        status_code=504,
                        details={"provider": "mistral"},
                    ) from exc
                except httpx.RequestError as exc:
                    if attempt_index < attempts - 1:
                        await _retry_sleep(attempt_index)
                        continue
                    raise ServiceError(
                        "provider_unavailable",
                        "Mistral request failed.",
                        status_code=503,
                        details={"provider": "mistral"},
                    ) from exc

                if response.status_code == 429:
                    if attempt_index < attempts - 1:
                        await _retry_sleep(
                            attempt_index,
                            retry_after=response.headers.get("Retry-After"),
                        )
                        continue
                    raise ServiceError(
                        "provider_rate_limited",
                        "Mistral rate limit was reached.",
                        status_code=429,
                        details={"provider": "mistral"},
                    )
                if response.status_code in {401, 403}:
                    raise ServiceError(
                        "provider_auth_failed",
                        "Mistral rejected the configured credentials.",
                        status_code=503,
                        details={"provider": "mistral"},
                    )
                if response.status_code >= 500 and attempt_index < attempts - 1:
                    await _retry_sleep(
                        attempt_index,
                        retry_after=response.headers.get("Retry-After"),
                    )
                    continue
                if response.status_code >= 400:
                    raise ServiceError(
                        "provider_error",
                        "Mistral returned an unusable response.",
                        status_code=502,
                        details={
                            "provider": "mistral",
                            "provider_status_code": response.status_code,
                        },
                    )
                try:
                    response_json = response.json()
                except ValueError as exc:
                    raise ServiceError(
                        "invalid_provider_response",
                        "Mistral response body was not valid JSON.",
                        status_code=502,
                        details={"provider": "mistral"},
                    ) from exc
                if not isinstance(response_json, dict):
                    raise ServiceError(
                        "invalid_provider_response",
                        "Mistral response body must be a JSON object.",
                        status_code=502,
                        details={"provider": "mistral"},
                    )
                return response_json
        raise ServiceError(
            "provider_error",
            "Mistral request failed after retries.",
            status_code=502,
            details={"provider": "mistral"},
        )


def _build_mistral_payload(
    request: ForecastAdjustmentRequest,
    settings: ServiceSettings,
) -> dict[str, Any]:
    return {
        "model": settings.mistral_model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(request)},
        ],
        "temperature": settings.temperature,
        "max_tokens": settings.max_output_tokens,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "forecast_adjustment_output",
                "schema": _FORECAST_OUTPUT_SCHEMA,
                "strict": True,
            },
        },
    }


def _system_prompt() -> str:
    return (
        "You are a forecasting adjustment component for Country Compare.\n"
        "Use only the provided history, baseline forecast, and constraints. "
        "Do not use web search, tools, retrieval, memorized external facts, "
        "or assumptions outside the input JSON. Return exactly the requested "
        "forecast years. Return finite numeric values only. Do not exceed the "
        "configured max adjustment percentage versus the baseline forecast.\n"
        "Return JSON only and follow the schema exactly."
    )


def _user_prompt(request: ForecastAdjustmentRequest) -> str:
    provider_input = {
        "request_id": request.request_id,
        "country": {"code": request.country_code, "name": request.country_name},
        "metric": {
            "id": request.metric_id,
            "name": request.metric_name,
            "unit": request.unit,
        },
        "history": [point.model_dump(mode="json") for point in request.history],
        "baseline_forecast": [
            point.model_dump(mode="json") for point in request.baseline_forecast
        ],
        "constraints": request.constraints.model_dump(mode="json"),
        "prompt_version": request.prompt_version,
    }
    return (
        "Adjust the baseline forecast only when the provided time series pattern "
        "supports a bounded adjustment.\nReturn the response as JSON with "
        "forecast_points, rationale, assumptions, and warnings.\n\n"
        f"Input JSON:\n{json.dumps(provider_input, ensure_ascii=False)}"
    )


def _extract_message_content(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ServiceError(
            "invalid_provider_response",
            "Mistral response did not contain choices.",
            status_code=502,
            details={"provider": "mistral"},
        )
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ServiceError(
            "invalid_provider_response",
            "Mistral choice was not an object.",
            status_code=502,
            details={"provider": "mistral"},
        )
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ServiceError(
            "invalid_provider_response",
            "Mistral choice did not contain a message object.",
            status_code=502,
            details={"provider": "mistral"},
        )
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    raise ServiceError(
        "invalid_provider_response",
        "Mistral message content was empty or not textual.",
        status_code=502,
        details={"provider": "mistral"},
    )


async def _retry_sleep(attempt_index: int, *, retry_after: str | None = None) -> None:
    await asyncio.sleep(_retry_delay_seconds(attempt_index, retry_after=retry_after))


def _retry_delay_seconds(
    attempt_index: int, *, retry_after: str | None = None
) -> float:
    retry_after_delay = _parse_retry_after_seconds(retry_after)
    if retry_after_delay is not None:
        return retry_after_delay
    base_delay = min(0.25 * (2**attempt_index), 2.0)
    jitter = random.uniform(0.0, base_delay * 0.25)
    return base_delay + jitter


def _parse_retry_after_seconds(raw_value: str | None) -> float | None:
    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value:
        return None
    try:
        delay = float(value)
    except ValueError:
        delay = _parse_retry_after_http_date_seconds(value)
    return min(max(delay, 0.0), 10.0)


def _parse_retry_after_http_date_seconds(value: str) -> float:
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return 0.0
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    delay = (retry_at - datetime.now(UTC)).total_seconds()
    return min(max(delay, 0.0), 10.0)
