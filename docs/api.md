# API Reference

The `v0.1 beta` FastAPI backend is read-only and exposes operational, metadata, comparison, scoring, and prediction endpoints.

Business endpoints use the `/api/v1` prefix. Operational endpoints are unversioned. Every response includes `X-Request-ID`; callers may provide this header and the API will echo it.

## Operational endpoints

### `GET /health`

Liveness check.

Expected success response:

```json
{
  "status": "ok",
  "service": "country-compare-api",
  "version": "0.1.0"
}
```

This endpoint should be lightweight and should not require loading or validating the dataset.

### `GET /ready`

Readiness check.

Readiness validates that the backend can serve real application traffic, including dataset availability and dataset-aware config validity.

Possible statuses:

- `200 OK` when ready
- `503 Service Unavailable` when dataset/config state is not ready

## Metadata endpoints

### `GET /api/v1/metadata/dataset`

Returns dataset summary and availability information.

### `GET /api/v1/metadata/countries`

Returns country selector options.

### `GET /api/v1/metadata/metrics`

Returns metric selector options.

### `GET /api/v1/metadata/years`

Returns available years.

### `GET /api/v1/metadata/profiles`

Returns scoring profile summaries.

## Comparison endpoints

### `POST /api/v1/compare/single-metric`

Compare countries for a single metric.

Example request:

```json
{
  "country_codes": ["ISR", "FRA", "USA"],
  "metric_id": "gdp_per_capita",
  "year_strategy": "latest_per_metric",
  "target_year": null,
  "top_n": null
}
```

### `POST /api/v1/compare/multi-metric`

Compare countries across multiple metrics.

Example request:

```json
{
  "country_codes": ["ISR", "FRA", "USA"],
  "metric_ids": ["gdp_per_capita", "life_expectancy"],
  "year_strategy": "latest_per_metric",
  "target_year": null,
  "top_n": null
}
```

### `POST /api/v1/score/profile`

Run weighted/profile scoring for selected countries.

Example request:

```json
{
  "country_codes": ["ISR", "FRA", "USA"],
  "profile_name": "economic_outlook",
  "year_strategy": "latest_per_metric",
  "target_year": null,
  "top_n": null
}
```

## Prediction endpoints

### `POST /api/v1/prediction/single-metric`

Forecast one metric for one or more countries.

Example request:

```json
{
  "country_codes": ["ISR", "FRA"],
  "metric_id": "gdp_per_capita",
  "horizon_years": 3,
  "method": "linear_trend",
  "fallback_method": "last_observed",
  "history_start_year": null,
  "history_end_year": null,
  "scenario_id": "baseline"
}
```

### `POST /api/v1/prediction/backtest`

Evaluate prediction behavior using holdout periods.

Example request:

```json
{
  "country_codes": ["ISR", "FRA"],
  "metric_id": "gdp_per_capita",
  "method": "linear_trend",
  "fallback_method": "last_observed",
  "holdout_years": 2,
  "scenario_id": "baseline"
}
```

### `POST /api/v1/prediction/compare/single-metric`

Compare countries by forecasted single-metric values.

Example request:

```json
{
  "country_codes": ["ISR", "FRA", "USA"],
  "metric_id": "gdp_per_capita",
  "forecast_year": 2027,
  "forecast_horizon": null,
  "horizon_years": 3,
  "method": "linear_trend",
  "fallback_method": "last_observed",
  "scenario_id": "baseline",
  "comparison_options": {
    "top_n": null
  }
}
```

### `POST /api/v1/prediction/compare/profile`

Compare countries by forecasted profile scores.

Example request:

```json
{
  "country_codes": ["ISR", "FRA", "USA"],
  "profile_name": "economic_outlook",
  "forecast_year": 2027,
  "forecast_horizon": null,
  "horizon_years": 3,
  "method": "linear_trend",
  "fallback_method": "last_observed",
  "scenario_id": "baseline",
  "comparison_options": {
    "top_n": null
  }
}
```

## Common result envelope

Computation endpoints return a flexible JSON-safe envelope:

```json
{
  "ok": true,
  "mode": "single_metric",
  "request": {},
  "summary": {},
  "metadata": {},
  "diagnostics": {},
  "warnings": [],
  "messages": [],
  "tables": {},
  "charts": {},
  "error": null
}
```

## Table payload format

Pandas DataFrames are serialized as JSON-safe table payloads:

```json
{
  "row_count": 3,
  "column_count": 8,
  "columns": ["country_code", "country_name", "metric_id", "year", "value"],
  "records": [],
  "records_truncated": false
}
```

Serialization expectations:

- `pd.NA`, `NaN`, and `NaT` become `null`
- numpy scalar values become Python scalar values
- dates/times become strings
- column order is preserved
- record truncation is supported

## Error response shape

Errors use a consistent shape:

```json
{
  "error": {
    "code": "invalid_metric",
    "message": "Unknown metric_id: foo",
    "details": {
      "metric_id": "foo"
    }
  }
}
```

## Read-only v0.1 beta boundary

The API does not expose write endpoints. It does not support config editing, scoring profile editing, dataset refresh, ingestion execution, or scheduled processing.


## Request IDs and errors

The API accepts inbound `X-Request-ID` values, generates one when missing, and returns the final value on every response. Access logs are structured JSON and include the request id, method, path, status code, and request duration. Unexpected exceptions are logged with stack traces server-side while client-facing error responses remain sanitized.
