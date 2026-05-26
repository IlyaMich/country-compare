from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class LLMForecastClientUnavailable(RuntimeError):
    """Raised when no LLM forecast client is configured."""


class LLMForecastResponseParseError(ValueError):
    """Raised when provider output cannot be parsed as a valid forecast response."""


@dataclass(frozen=True, slots=True)
class LLMForecastPoint:
    year: int
    value: float

    def __post_init__(self) -> None:
        year = int(self.year)
        value = float(self.value)

        if not math.isfinite(value):
            raise ValueError("forecast point value must be finite")

        object.__setattr__(self, "year", year)
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class LLMForecastRequest:
    country_code: str
    country_name: str | None
    metric_id: str
    metric_name: str | None
    unit: str | None
    history: list[dict[str, float | int | str | None]]
    baseline_forecast: list[dict[str, float | int]]
    horizon_years: int
    prompt_version: str


@dataclass(frozen=True, slots=True)
class LLMForecastResponse:
    forecast_points: list[LLMForecastPoint]
    rationale: str = ""
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_provider_metadata: dict[str, object] = field(default_factory=dict)


class LLMForecastClient(Protocol):
    def forecast(self, request: LLMForecastRequest) -> LLMForecastResponse:
        """Return a structured forecast response for a prepared forecast request."""


@runtime_checkable
class LLMForecastAvailabilityClient(Protocol):
    def is_available(self) -> bool:
        """Return whether the configured LLM client is currently usable."""


class DisabledLLMForecastClient:
    def forecast(self, request: LLMForecastRequest) -> LLMForecastResponse:
        raise LLMForecastClientUnavailable("no LLM forecast client is configured")


def llm_response_from_json(payload: str) -> LLMForecastResponse:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise LLMForecastResponseParseError("LLM response was not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise LLMForecastResponseParseError("LLM response JSON must be an object")

    points_payload = parsed.get("forecast_points")
    if not isinstance(points_payload, list):
        raise LLMForecastResponseParseError(
            "LLM response must contain a forecast_points list"
        )

    forecast_points: list[LLMForecastPoint] = []
    for item in points_payload:
        if not isinstance(item, dict):
            raise LLMForecastResponseParseError(
                "each forecast point must be a JSON object"
            )

        if "year" not in item or "value" not in item:
            raise LLMForecastResponseParseError(
                "each forecast point must include year and value"
            )

        try:
            forecast_points.append(
                LLMForecastPoint(year=int(item["year"]), value=float(item["value"]))
            )
        except (TypeError, ValueError) as exc:
            raise LLMForecastResponseParseError(
                "forecast point year/value could not be parsed"
            ) from exc

    metadata_payload = parsed.get("raw_provider_metadata", {})
    metadata = dict(metadata_payload) if isinstance(metadata_payload, dict) else {}

    return LLMForecastResponse(
        forecast_points=forecast_points,
        rationale=_optional_text(parsed.get("rationale")),
        assumptions=_string_list(parsed.get("assumptions")),
        warnings=_string_list(parsed.get("warnings")),
        raw_provider_metadata=metadata,
    )


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    return [str(item) for item in value if item is not None]
