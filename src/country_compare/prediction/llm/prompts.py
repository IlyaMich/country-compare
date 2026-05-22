from __future__ import annotations

from country_compare.prediction.llm.client import LLMForecastRequest

LLM_FORECAST_PROMPT_VERSION = "llm_forecast_v1"


def build_llm_forecast_prompt(request: LLMForecastRequest) -> str:
    """Build a compact provider-neutral prompt for a structured forecast response.

    This prompt is intentionally simple because the first implementation is
    mock/stub-first. Real provider adapters can use this text or replace it with
    provider-specific structured-output instructions later.
    """

    return (
        "You are assisting with an experimental country metric forecast.\n"
        "Return strict JSON only with keys: forecast_points, rationale, assumptions, "
        "warnings.\n"
        "The forecast_points array must contain exactly the requested future years "
        "and numeric values.\n"
        "Do not add years that were not requested.\n"
        "Use the deterministic baseline forecast as the anchor and only make bounded "
        "adjustments when the provided history supports them.\n\n"
        f"Country: {request.country_name or request.country_code}\n"
        f"Metric: {request.metric_name or request.metric_id}\n"
        f"Unit: {request.unit or 'unknown'}\n"
        f"Horizon years: {request.horizon_years}\n"
        f"History: {request.history}\n"
        f"Baseline forecast: {request.baseline_forecast}\n"
    )
