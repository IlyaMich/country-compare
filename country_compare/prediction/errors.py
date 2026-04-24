from __future__ import annotations

from enum import Enum
from typing import Any


class PredictionErrorCode(str, Enum):
    """Stable error codes for prediction request, preparation, and forecasting failures."""

    INVALID_HORIZON = "invalid_horizon"
    UNSUPPORTED_METHOD = "unsupported_method"
    MISSING_METRIC = "missing_metric"
    MISSING_COUNTRY = "missing_country"
    EMPTY_SERIES = "empty_series"
    INSUFFICIENT_HISTORY = "insufficient_history"
    DUPLICATE_SERIES_YEAR = "duplicate_series_year"
    NON_NUMERIC_VALUE = "non_numeric_value"
    UNSUPPORTED_SERIES_SHAPE = "unsupported_series_shape"
    FORECASTING_FAILED = "forecasting_failed"
    COMPARISON_BRIDGE_FAILED = "comparison_bridge_failed"
    EVALUATION_FAILED = "evaluation_failed"
    UNEXPECTED_PREDICTION_ERROR = "unexpected_prediction_error"


class PredictionException(ValueError):
    """Raised when prediction cannot be completed for a structured, known reason."""

    def __init__(
        self,
        code: PredictionErrorCode | str,
        message: str,
        *,
        country_code: str | None = None,
        metric_id: str | None = None,
        year: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = PredictionErrorCode(code)
        self.message = message
        self.country_code = country_code
        self.metric_id = metric_id
        self.year = year
        self.details = details or {}
        super().__init__(f"{self.code.value}: {message}")
