"""
This test file should run successfully in environments with or without sklearn installed.
"""

from __future__ import annotations

from country_compare.prediction.ml_forecasters import is_elasticnet_available
from country_compare.prediction.registry import list_forecasters


def test_elasticnet_registration_matches_optional_dependency() -> None:
    assert ("elasticnet_trend" in list_forecasters()) is is_elasticnet_available()
