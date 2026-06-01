from __future__ import annotations

import pytest
from pydantic import ValidationError

from llm_forecast_service.schemas import ForecastAdjustmentOutput


def test_provider_output_rejects_too_many_warnings() -> None:
    with pytest.raises(ValidationError):
        ForecastAdjustmentOutput(
            forecast_points=[{"year": 2030, "value": 100.0}],
            warnings=["w1", "w2", "w3", "w4", "w5", "w6"],
        )
