from __future__ import annotations

import uuid
from typing import Any

import httpx

from country_compare.prediction.llm.client import (
    LLMForecastPoint,
    LLMForecastRequest,
    LLMForecastResponse,
)


class RemoteLLMForecastError(RuntimeError):
    """Raised when the remote LLM forecast service cannot return a usable response."""


class RemoteLLMForecastClient:
    def __init__(
        self,
        *,
        service_url: str,
        service_token: str,
        timeout_seconds: float,
        max_adjustment_pct: float,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._service_url = service_url.rstrip("/")
        self._service_token = service_token
        self._timeout_seconds = float(timeout_seconds)
        self._max_adjustment_pct = float(max_adjustment_pct)
        self._http_client = http_client

    def is_available(self) -> bool:
        try:
            capabilities = self.capabilities()
        except RemoteLLMForecastError:
            return False

        return (
            bool(capabilities.get("supports_bounded_adjustment"))
            and bool(capabilities.get("supports_structured_output"))
            and int(capabilities.get("max_series_per_request", 0)) >= 1
        )

    def capabilities(self) -> dict[str, Any]:
        payload = self._request_json("GET", "/v1/capabilities")
        if not isinstance(payload, dict):
            raise RemoteLLMForecastError(
                "LLM service capabilities response was invalid"
            )
        return payload

    def forecast(self, request: LLMForecastRequest) -> LLMForecastResponse:
        payload = self._forecast_request_payload(request)
        response_payload = self._request_json(
            "POST",
            "/v1/forecast/adjust",
            json=payload,
        )
        return _forecast_response_from_service_payload(response_payload)

    def _forecast_request_payload(self, request: LLMForecastRequest) -> dict[str, Any]:
        baseline_forecast = [
            _point_payload(point) for point in request.baseline_forecast
        ]
        allowed_years = [int(point["year"]) for point in baseline_forecast]

        return {
            "request_id": str(uuid.uuid4()),
            "country_code": request.country_code,
            "country_name": request.country_name or request.country_code,
            "metric_id": request.metric_id,
            "metric_name": request.metric_name or request.metric_id,
            "unit": request.unit,
            "history": [_point_payload(point) for point in request.history],
            "baseline_forecast": baseline_forecast,
            "constraints": {
                "max_adjustment_pct": self._max_adjustment_pct,
                "horizon_years": request.horizon_years,
                "allowed_years": allowed_years,
            },
            "prompt_version": request.prompt_version,
        }

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._service_url}{path}"
        headers = {"Authorization": f"Bearer {self._service_token}"}

        try:
            response = self._send_request(method, url, headers=headers, json=json)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RemoteLLMForecastError("LLM service request timed out") from exc
        except httpx.HTTPStatusError as exc:
            message = _http_error_message(exc.response)
            raise RemoteLLMForecastError(message) from exc
        except httpx.HTTPError as exc:
            raise RemoteLLMForecastError("LLM service request failed") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise RemoteLLMForecastError(
                "LLM service response was not valid JSON"
            ) from exc

    def _send_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None,
    ) -> httpx.Response:
        if self._http_client is not None:
            return self._http_client.request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=self._timeout_seconds,
            )

        with httpx.Client(timeout=self._timeout_seconds) as client:
            return client.request(method, url, headers=headers, json=json)


def _point_payload(point: dict[str, Any]) -> dict[str, float | int]:
    return {
        "year": int(point["year"]),
        "value": float(point["value"]),
    }


def _forecast_response_from_service_payload(payload: Any) -> LLMForecastResponse:
    if not isinstance(payload, dict):
        raise RemoteLLMForecastError("LLM service forecast response was invalid")

    points_payload = payload.get("forecast_points")
    if not isinstance(points_payload, list):
        raise RemoteLLMForecastError(
            "LLM service response did not include forecast_points"
        )

    forecast_points: list[LLMForecastPoint] = []
    for item in points_payload:
        if not isinstance(item, dict):
            raise RemoteLLMForecastError(
                "LLM service returned an invalid forecast point"
            )
        try:
            forecast_points.append(
                LLMForecastPoint(
                    year=int(item["year"]),
                    value=float(item["value"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RemoteLLMForecastError(
                "LLM service returned an unparseable forecast point"
            ) from exc

    metadata = payload.get("metadata", {})
    return LLMForecastResponse(
        forecast_points=forecast_points,
        rationale=_text(payload.get("rationale")),
        assumptions=_string_list(payload.get("assumptions")),
        warnings=_string_list(payload.get("warnings")),
        raw_provider_metadata=metadata if isinstance(metadata, dict) else {},
    )


def _http_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"LLM service returned HTTP {response.status_code}"

    if not isinstance(payload, dict):
        return f"LLM service returned HTTP {response.status_code}"

    error = payload.get("error")
    if isinstance(error, dict):
        code = _text(error.get("code")) or "remote_error"
        message = _text(error.get("message")) or "LLM service request failed"
        return f"LLM service error {code}: {message}"

    return f"LLM service returned HTTP {response.status_code}"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]
