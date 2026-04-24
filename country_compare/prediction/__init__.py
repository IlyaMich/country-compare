from country_compare.prediction.comparison_bridge import (
    compare_predicted_multi_metric,
    compare_predicted_profile,
    compare_predicted_single_metric,
)
from country_compare.prediction.errors import PredictionErrorCode, PredictionException
from country_compare.prediction.models import (
    BacktestRequest,
    BacktestResult,
    ForecastContext,
    ForecastOptions,
    ForecasterInfo,
    MultiSeriesPredictionRequest,
    PredictedComparisonResult,
    PredictionDiagnosticStatus,
    PredictionDiagnostics,
    PredictionError,
    PredictionMethod,
    PredictionResult,
    SingleMetricPredictionRequest,
)
from country_compare.prediction.evaluation import backtest_series
from country_compare.prediction.multi_metric import (
    predict_metric_country_grid,
    predict_metrics_for_country,
    predict_single_metric_for_countries,
)
from country_compare.prediction.single_metric import predict_single_metric
from country_compare.prediction.visualization import (
    build_actual_vs_predicted_dataframe,
    build_forecast_table_dataframe,
    build_line_chart_dataframe,
)
from country_compare.prediction.summaries import (
    build_backtest_result_summary,
    build_forecaster_info_summary,
    build_predicted_comparison_result_summary,
    build_prediction_diagnostic_summary,
    build_prediction_diagnostics_collection_summary,
    build_prediction_result_summary,
    list_available_prediction_methods,
    list_forecast_horizons,
    list_forecast_years,
    prediction_exception_to_dict,
)

__all__ = [
    "PredictionErrorCode",
    "PredictionException",
    "BacktestRequest",
    "BacktestResult",
    "ForecastContext",
    "ForecastOptions",
    "ForecasterInfo",
    "MultiSeriesPredictionRequest",
    "PredictedComparisonResult",
    "PredictionDiagnosticStatus",
    "PredictionDiagnostics",
    "PredictionError",
    "PredictionMethod",
    "PredictionResult",
    "SingleMetricPredictionRequest",
    "predict_single_metric",
    "backtest_series",
    "predict_single_metric_for_countries",
    "predict_metrics_for_country",
    "predict_metric_country_grid",
    "compare_predicted_single_metric",
    "compare_predicted_multi_metric",
    "compare_predicted_profile",
    "build_line_chart_dataframe",
    "build_actual_vs_predicted_dataframe",
    "build_forecast_table_dataframe",
    "build_backtest_result_summary",
    "build_forecaster_info_summary",
    "build_predicted_comparison_result_summary",
    "build_prediction_diagnostic_summary",
    "build_prediction_diagnostics_collection_summary",
    "build_prediction_result_summary",
    "list_available_prediction_methods",
    "list_forecast_horizons",
    "list_forecast_years",
    "prediction_exception_to_dict",
]
