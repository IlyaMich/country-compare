from __future__ import annotations

from typing import Final

SIDEBAR_TITLE: Final[str] = "Country Compare"
PAGE_RADIO_LABEL: Final[str] = "Page"
DEBUG_CHECKBOX_LABEL: Final[str] = "Debug mode"
RESERVED_PAGE_INFO: Final[str] = "This page is reserved for a later UI phase."

BACKEND_CAPTION_PREFIX: Final[str] = "Backend"
METRICS_CONFIG_CAPTION_PREFIX: Final[str] = "Metrics config"
SCORING_CONFIG_CAPTION_PREFIX: Final[str] = "Scoring config"

PREDICTION_PAGE_TITLE: Final[str] = "Prediction"
PREDICTION_PAGE_CAPTION: Final[str] = (
    "Run forecast, predicted comparison, and backtest workflows through the "
    "service layer."
)

PREDICTION_TAB_SINGLE_FORECAST: Final[str] = "Single Forecast"
PREDICTION_TAB_MULTI_COUNTRY_FORECAST: Final[str] = "Multi-Country Forecast"
PREDICTION_TAB_PREDICTED_COMPARISON: Final[str] = "Predicted Comparison"
PREDICTION_TAB_BACKTEST: Final[str] = "Backtest"

PREDICTION_TAB_LABELS: Final[tuple[str, ...]] = (
    PREDICTION_TAB_SINGLE_FORECAST,
    PREDICTION_TAB_MULTI_COUNTRY_FORECAST,
    PREDICTION_TAB_PREDICTED_COMPARISON,
    PREDICTION_TAB_BACKTEST,
)

PREDICTION_METHODS_METRIC_LABEL: Final[str] = "Methods"
PREDICTION_COUNTRIES_METRIC_LABEL: Final[str] = "Countries"
PREDICTION_METRICS_METRIC_LABEL: Final[str] = "Metrics"
PREDICTION_LATEST_YEAR_METRIC_LABEL: Final[str] = "Latest year"
PREDICTION_METHOD_CATALOG_EXPANDER_LABEL: Final[str] = "Prediction method catalog"

PREDICTION_FORECAST_HORIZON_YEARS_LABEL: Final[str] = "Forecast horizon (years)"
PREDICTION_HOLDOUT_YEARS_LABEL: Final[str] = "Holdout years"

RUN_SINGLE_FORECAST_BUTTON_LABEL: Final[str] = "Run single forecast"
RUN_MULTI_COUNTRY_FORECAST_BUTTON_LABEL: Final[str] = "Run multi-country forecast"
RUN_PREDICTED_COMPARISON_BUTTON_LABEL: Final[str] = "Run predicted comparison"
RUN_BACKTEST_BUTTON_LABEL: Final[str] = "Run backtest"

SINGLE_FORECAST_EMPTY_MESSAGE: Final[str] = (
    "Run a single-country single-metric forecast to see results here."
)
MULTI_COUNTRY_FORECAST_EMPTY_MESSAGE: Final[str] = (
    "Run a multi-country forecast to see batch results here."
)
PREDICTED_COMPARISON_EMPTY_MESSAGE: Final[str] = (
    "Run a predicted comparison to see ranking output here."
)
BACKTEST_EMPTY_MESSAGE: Final[str] = (
    "Run a holdout backtest to see evaluation metrics here."
)

PREDICTED_COMPARISON_TYPE_LABEL: Final[str] = "Comparison type"
PREDICTED_COMPARISON_MODE_SINGLE_METRIC_LABEL: Final[str] = "Single Metric"
PREDICTED_COMPARISON_MODE_MULTI_METRIC_LABEL: Final[str] = "Multi Metric"
PREDICTED_COMPARISON_MODE_PROFILE_LABEL: Final[str] = "Profile"
PREDICTED_COMPARISON_MODE_SINGLE_METRIC: Final[str] = (
    "predicted_single_metric_comparison"
)
PREDICTED_COMPARISON_MODE_MULTI_METRIC: Final[str] = "predicted_multi_metric_comparison"
PREDICTED_COMPARISON_MODE_PROFILE: Final[str] = "predicted_profile_comparison"

PREDICTED_COMPARISON_MODES: Final[tuple[tuple[str, str], ...]] = (
    (
        PREDICTED_COMPARISON_MODE_SINGLE_METRIC_LABEL,
        PREDICTED_COMPARISON_MODE_SINGLE_METRIC,
    ),
    (
        PREDICTED_COMPARISON_MODE_MULTI_METRIC_LABEL,
        PREDICTED_COMPARISON_MODE_MULTI_METRIC,
    ),
    (
        PREDICTED_COMPARISON_MODE_PROFILE_LABEL,
        PREDICTED_COMPARISON_MODE_PROFILE,
    ),
)

PREDICTED_COMPARISON_FORECAST_SELECTION_LABEL: Final[str] = "Select forecast by"
PREDICTED_COMPARISON_FORECAST_SELECTION_HORIZON: Final[str] = "Horizon"
PREDICTED_COMPARISON_FORECAST_SELECTION_YEAR: Final[str] = "Year"
PREDICTED_COMPARISON_FORECAST_SELECTION_OPTIONS: Final[tuple[str, ...]] = (
    PREDICTED_COMPARISON_FORECAST_SELECTION_HORIZON,
    PREDICTED_COMPARISON_FORECAST_SELECTION_YEAR,
)
PREDICTED_COMPARISON_FORECAST_HORIZON_LABEL: Final[str] = "Forecast horizon to compare"
PREDICTED_COMPARISON_FORECAST_YEAR_LABEL: Final[str] = "Forecast year to compare"

COMPARISON_SUMMARY_HEADING: Final[str] = "Comparison summary"
RANKED_COMPARISON_SUMMARY_HEADING: Final[str] = "Ranked comparison summary"
COMPARED_ROWS_METRIC_LABEL: Final[str] = "Compared rows"
RANKED_ROWS_METRIC_LABEL: Final[str] = "Ranked rows"
TOP_RESULT_METRIC_LABEL: Final[str] = "Top result"
TOP_VALUE_METRIC_LABEL: Final[str] = "Top value"
COMPARISON_NO_NUMERIC_VALUE_MESSAGE: Final[str] = (
    "No numeric comparison value was available for a visual summary."
)
PREDICTED_COMPARISON_NO_RANKED_ROWS_MESSAGE: Final[str] = (
    "No ranked comparison rows are available to summarize."
)
PREDICTED_COMPARISON_TABLE_HEADING: Final[str] = "Predicted comparison table"
MAIN_RESULT_TABLE_HEADING: Final[str] = "Main result table"


def backend_caption(store_backend: str) -> str:
    return f"{BACKEND_CAPTION_PREFIX}: {store_backend}"


def metrics_config_caption(path: object) -> str:
    return f"{METRICS_CONFIG_CAPTION_PREFIX}: {path}"


def scoring_config_caption(path: object) -> str:
    return f"{SCORING_CONFIG_CAPTION_PREFIX}: {path}"
