# Prediction Behavior and Limitations

Country Compare prediction workflows provide baseline statistical projections and backtesting tools.

Predictions are designed to support exploration and comparison. They are not guarantees, recommendations, or authoritative forecasts.

## Prediction modes

### Single forecast

Forecasts one metric for one or more countries over a selected horizon.

Typical outputs:

- forecast table
- actual-and-forecast table
- chart-ready line data
- diagnostics
- warnings and messages

### Multi-country forecast

Runs the same forecast workflow across multiple selected countries.

Typical outputs:

- per-country forecast rows
- combined chart-ready data where available
- diagnostics for each series
- aggregate quality/limitations context

### Predicted comparison

Uses forecasted values to compare countries.

Supported comparison concepts may include:

- single forecasted metric comparison
- forecasted multi-metric comparison
- forecasted profile scoring comparison

The UI shows ranked summaries and bar charts when result tables contain usable ranking/value/score data.

### Backtest

Backtesting evaluates forecast behavior by holding out recent historical observations and comparing predictions against actual values.

Typical outputs:

- actual-vs-predicted table
- error metrics
- diagnostics
- quality/evaluation context

## Methods and fallback behavior

Prediction workflows can use a configured method and fallback method.

A fallback method may be used when the preferred method cannot produce a reliable result for a series, for example due to sparse history.

Common diagnostic concepts include:

- selected method
- fallback method
- status
- warning
- failed series
- insufficient observations

## Quality and limitations panels

The Streamlit UI surfaces quality and limitation information close to prediction outputs.

The panel should help users understand:

- whether the forecast is based on enough history
- whether fallback methods were used
- whether any series failed
- whether diagnostics contain warnings
- how much confidence to place in the output
- how to interpret backtest error metrics

## Important limitations

- Forecasts are baseline statistical projections.
- Forecasts do not include causal modeling.
- Forecasts do not account for future shocks, policy changes, wars, pandemics, or other major structural breaks unless those effects are already reflected in the historical data.
- Sparse or stale historical data can reduce reliability.
- Backtest performance is historical and does not guarantee future performance.
- A high-ranked forecasted country is not necessarily the best policy or investment choice.

## Visualization behavior

Local mode may have access to in-process objects. HTTP-backed/container mode receives JSON-safe table payloads.

For container-friendly behavior, prediction charts are rebuilt in the Streamlit layer from returned data using Streamlit-native charts, such as:

- actual-vs-forecast line charts
- actual-vs-predicted backtest line charts
- predicted comparison bar charts

If returned data is not chartable, the UI should show tables and clear explanatory text rather than failing.
