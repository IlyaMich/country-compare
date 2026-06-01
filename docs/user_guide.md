# User guide

Country Compare lets you explore country-level metrics, weighted profiles, and forecasts through a Streamlit UI.

## Start the UI

Local in-process mode:

```bash
country-compare ui
```

HTTP-backed mode:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

## Compare one metric

1. Select countries.
2. Select a metric.
3. Choose a year strategy or target year.
4. Optionally set `top_n`.
5. Run the comparison.
6. Review ranking, source/unit metadata, warnings, and diagnostics.

## Compare multiple metrics

1. Select countries.
2. Select multiple metrics.
3. Choose a year strategy or target year.
4. Run the comparison.
5. Review normalized/ranked outputs and metric diagnostics.

## Use profile scoring

1. Select countries.
2. Select a scoring profile.
3. Choose year options.
4. Run scoring.
5. Review profile metric membership, ranking, and diagnostics.

Profiles are defined in configuration and should not be edited from the current read-only API/UI runtime.

## Forecast one metric

1. Select countries and a metric.
2. Choose a method such as `linear_trend`.
3. Choose fallback method, usually `last_observed`.
4. Set forecast horizon.
5. Run the forecast.
6. Review actuals, predictions, warnings, and diagnostics.

Forecasts are baseline projections. They are sensitive to sparse histories, stale data, methodology changes, and external shocks.

## Backtest

Use backtesting to see how a method performs against recent known data. Select holdout years and review prediction errors and diagnostics.

## Predicted comparisons

Predicted comparisons rank countries using forecast values. You can compare:

- one future metric;
- a profile based on future values;
- multiple future metrics.

## Optional LLM forecasts

`llm_forecast` appears only when the optional private service is enabled and ready. It performs bounded adjustments over deterministic baseline forecasts and is experimental. Always review its warnings and diagnostics.

## Exports

Result panels support export-first workflows:

- result tables as CSV;
- diagnostics as JSON;
- summaries as Markdown.

Exports are produced from the UI/service result payloads. The current read-only backend does not persist server-side export files.

## Interpreting warnings

Warnings indicate limitations such as missing data, sparse histories, fallback use, old observations, truncated records, or unavailable optional methods. Treat them as part of the result, not as noise.
