# User Guide

This guide explains how to use Country Compare from the Streamlit UI.

## Start the UI

Local mode:

```bash
country-compare ui
```

Docker Compose mode:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:8501
```

## Comparison workflows

### Single-metric comparison

Use this workflow to compare selected countries for one metric.

Typical steps:

1. Choose countries.
2. Choose a metric.
3. Choose year strategy or target year.
4. Run comparison.
5. Review summary metrics, chart, and detailed table.
6. Export results where export controls are available.

The UI shows Streamlit-native visualizations when the returned table contains chartable country/value data.

### Multi-metric comparison

Use this workflow to compare selected countries across multiple metrics.

Typical steps:

1. Choose countries.
2. Choose multiple metrics.
3. Choose year strategy or target year.
4. Run comparison.
5. Review table and chart if the returned data shape supports visualization.

If the result shape is not chartable, the UI should preserve the detailed table and avoid failing.

### Weighted/profile scoring

Use this workflow to score countries using a configured scoring profile.

Typical steps:

1. Choose countries.
2. Choose a scoring profile.
3. Run scoring.
4. Review score/rank summary, chart, and detailed table.
5. Export results where available.

## Prediction workflows

### Single forecast

Forecast one metric for one or more countries.

The UI may show:

- quality/limitations panel
- actual-vs-forecast chart
- forecast table
- diagnostics
- export controls

### Multi-country forecast

Forecast one metric for multiple countries.

The UI may show a combined chart and table where returned data supports it.

### Predicted comparison

Compare countries using forecasted values or forecasted profile scores.

The UI may show:

- prediction quality/limitations
- ranked summary
- bar chart
- detailed table
- diagnostics
- export controls

### Backtest

Evaluate prediction behavior against held-out historical data.

The UI may show:

- quality/evaluation context
- error metrics
- actual-vs-predicted chart
- detailed actual-vs-predicted table
- diagnostics

## Interpreting predictions

Predictions are baseline statistical projections, not guarantees.

Use the quality and limitation panels to understand:

- sparse history
- fallback method use
- failed series
- stale or limited data
- warning diagnostics
- backtest error metrics

## Exports

Where export controls are available, they should continue to work in both local and HTTP-backed modes.

Exports should preserve existing result tables and should not depend on live matplotlib figure objects in HTTP/container mode.
