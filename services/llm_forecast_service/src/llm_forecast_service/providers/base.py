from __future__ import annotations

from typing import Protocol

from llm_forecast_service.schemas import (
    ForecastAdjustmentOutput,
    ForecastAdjustmentRequest,
)


class LLMProvider(Protocol):
    def generate_adjustment(
        self, request: ForecastAdjustmentRequest
    ) -> ForecastAdjustmentOutput: ...


class BaselineEchoProvider:
    """Temporary PR1 provider that performs no external LLM call."""

    def generate_adjustment(
        self, request: ForecastAdjustmentRequest
    ) -> ForecastAdjustmentOutput:
        return ForecastAdjustmentOutput(
            forecast_points=request.baseline_forecast,
            rationale=(
                "Baseline echo provider used by the service skeleton; "
                "no external LLM call was made."
            ),
            assumptions=["The deterministic baseline is returned unchanged."],
            warnings=["LLM provider integration is not enabled in this service slice."],
        )
