# Prediction workflows

Prediction features provide baseline statistical projections, backtesting, and predicted comparisons. Forecast outputs are not guarantees; they are scenario-oriented estimates based on available historical data.

## Available workflow families

- Single-metric forecasts for one or more countries.
- Holdout backtesting for a country/metric series.
- Predicted single-metric comparisons.
- Predicted profile comparisons.
- Predicted multi-metric comparisons.

## API endpoints

```text
POST /api/v1/prediction/single-metric
POST /api/v1/prediction/backtest
POST /api/v1/prediction/compare/single-metric
POST /api/v1/prediction/compare/profile
POST /api/v1/prediction/compare/multi-metric
```

## Common method fields

| Field | Meaning |
| --- | --- |
| `method` | Primary prediction method, such as `linear_trend` or `llm_forecast` when enabled. |
| `fallback_method` | Method used when primary method cannot produce a safe result, commonly `last_observed`. |
| `horizon_years` | Number of future periods to forecast. Limited by API settings. |
| `history_start_year` / `history_end_year` | Optional historical window. |
| `scenario_id` | Scenario label, commonly `baseline`. |
| `include_actuals` | Include actual historical observations in forecast output. |
| `fail_fast` | Stop on first per-country failure or collect diagnostics and continue. |

## Quality guidance

Forecast quality depends on:

- history length;
- missingness;
- stale data;
- metric methodology changes;
- country structural breaks;
- external shocks not present in history;
- unit/scale correctness.

The UI and API should surface warnings and diagnostics instead of hiding uncertainty.

## Backtesting

Backtesting with holdout years estimates how a method would have performed on recent known data. Use it to compare methods or diagnose whether a series is too sparse or unstable.

Example request:

```json
{
  "country_code": "ISR",
  "country_codes": ["ISR"],
  "metric_id": "gdp_per_capita",
  "method": "linear_trend",
  "fallback_method": "last_observed",
  "holdout_years": 2,
  "history_start_year": null,
  "history_end_year": null,
  "scenario_id": "baseline"
}
```

## Predicted comparisons

Predicted comparisons convert forecast outputs back into comparison/scoring workflows. The API supports choosing a specific `forecast_year` or `forecast_horizon`; comparison options such as `top_n` are applied after forecast values are selected.

## LLM forecasts

`llm_forecast` is optional and experimental. It should only appear when backend gating succeeds. It performs bounded adjustments on top of deterministic forecasts and should always be presented with limitations and diagnostics.
