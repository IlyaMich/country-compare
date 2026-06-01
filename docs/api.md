# API reference

The Country Compare FastAPI backend is a read-only adapter over the service/domain core. Business endpoints are versioned under `/api/v1`; operational endpoints are unversioned.

## Operational endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness. Returns process/API version information. |
| `GET` | `/ready` | Strict readiness for serving comparison/prediction traffic. Validates dataset and config readiness. |
| `GET` | `/ready/llm` | Backend-to-LLM-service readiness. Does not run a forecast. |
| `GET` | `/metrics` | Prometheus-compatible metrics endpoint when enabled. Usually excluded from OpenAPI schema. |

## Metadata endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/metadata/dataset` | Dataset existence, backend, row/country/metric/year counts, checksum, schema status, categories. |
| `GET` | `/api/v1/metadata/countries` | Available countries. |
| `GET` | `/api/v1/metadata/metrics` | Available metrics, categories, and units. |
| `GET` | `/api/v1/metadata/years` | Available years and min/max year. |
| `GET` | `/api/v1/metadata/profiles` | Scoring profiles and metric membership. |
| `GET` | `/api/v1/metadata/prediction-methods` | Runtime prediction method options, including gated methods such as `llm_forecast` when available. |

## Comparison and scoring endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/compare/single-metric` | Compare countries on one metric. |
| `POST` | `/api/v1/compare/multi-metric` | Compare countries across selected metrics. |
| `POST` | `/api/v1/score/profile` | Score countries using a configured weighted profile. |

## Prediction endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/prediction/single-metric` | Forecast one metric for one or more countries. |
| `POST` | `/api/v1/prediction/backtest` | Run holdout backtest for a country/metric series. |
| `POST` | `/api/v1/prediction/compare/single-metric` | Compare countries using a future forecast for one metric. |
| `POST` | `/api/v1/prediction/compare/profile` | Compare countries using future forecasts and a scoring profile. |
| `POST` | `/api/v1/prediction/compare/multi-metric` | Compare countries using selected future forecasts for multiple metrics. |

## Authentication

Set `COUNTRY_COMPARE_API_KEY` to require bearer-token access for protected endpoints.

```bash
curl -H "Authorization: Bearer $COUNTRY_COMPARE_API_KEY" http://localhost:8000/api/v1/metadata/dataset
```

When the UI talks to a protected backend, set the same key in the UI environment.

## Request IDs

The backend accepts `X-Request-ID` and returns `X-Request-ID` on responses. Supply one from callers that already have correlation IDs:

```bash
curl -H "X-Request-ID: demo-123" http://localhost:8000/health
```

## Result envelope

Computation endpoints return a common JSON-safe envelope:

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

Table payloads have stable shape:

```json
{
  "row_count": 3,
  "column_count": 8,
  "columns": ["country_code", "country_name", "metric_id", "year", "value"],
  "records": [],
  "records_truncated": false
}
```

Serialization rules:

- `pd.NA`, `NaN`, and `NaT` become JSON `null`.
- numpy scalars become Python scalars.
- dates and datetimes become strings.
- column order is preserved.
- large table records may be truncated according to `COUNTRY_COMPARE_API_MAX_RECORDS`.

## Error shape

Expected errors use a stable error object inside the envelope or response body:

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

Typical status mapping:

- `400` for invalid request parameters or violated limits.
- `404` for missing countries, metrics, or profiles.
- `409` for invalid config/dataset/state.
- `500` for unexpected server errors with sanitized client messages.
- `503` for readiness failures.

## Examples

### Compare a single metric

```bash
curl -s http://localhost:8000/api/v1/compare/single-metric \
  -H 'Content-Type: application/json' \
  -d '{
    "country_codes": ["ISR", "FRA", "USA"],
    "metric_id": "gdp_per_capita",
    "year_strategy": "latest_per_metric",
    "target_year": null,
    "top_n": null
  }'
```

### Compare multiple metrics

```bash
curl -s http://localhost:8000/api/v1/compare/multi-metric \
  -H 'Content-Type: application/json' \
  -d '{
    "country_codes": ["ISR", "FRA", "USA"],
    "metric_ids": ["gdp_per_capita", "life_expectancy"],
    "year_strategy": "latest_per_metric",
    "target_year": null,
    "top_n": null
  }'
```

### Score by profile

```bash
curl -s http://localhost:8000/api/v1/score/profile \
  -H 'Content-Type: application/json' \
  -d '{
    "country_codes": ["ISR", "FRA", "USA"],
    "profile_name": "economic_outlook",
    "year_strategy": "latest_per_metric",
    "target_year": null,
    "top_n": null
  }'
```

### Forecast one metric

```bash
curl -s http://localhost:8000/api/v1/prediction/single-metric \
  -H 'Content-Type: application/json' \
  -d '{
    "country_codes": ["ISR", "FRA"],
    "metric_id": "gdp_per_capita",
    "horizon_years": 3,
    "method": "linear_trend",
    "fallback_method": "last_observed",
    "include_actuals": true,
    "history_start_year": null,
    "history_end_year": null,
    "fail_fast": false,
    "scenario_id": "baseline"
  }'
```

### Backtest

```bash
curl -s http://localhost:8000/api/v1/prediction/backtest \
  -H 'Content-Type: application/json' \
  -d '{
    "country_code": "ISR",
    "country_codes": ["ISR"],
    "metric_id": "gdp_per_capita",
    "method": "linear_trend",
    "fallback_method": "last_observed",
    "holdout_years": 2,
    "history_start_year": null,
    "history_end_year": null,
    "scenario_id": "baseline"
  }'
```

### Predicted multi-metric comparison

```bash
curl -s http://localhost:8000/api/v1/prediction/compare/multi-metric \
  -H 'Content-Type: application/json' \
  -d '{
    "country_codes": ["ISR", "FRA", "USA"],
    "metric_ids": ["gdp_per_capita", "life_expectancy"],
    "forecast_year": 2027,
    "forecast_horizon": null,
    "horizon_years": 3,
    "method": "linear_trend",
    "fallback_method": "last_observed",
    "scenario_id": "baseline",
    "comparison_options": {"top_n": null}
  }'
```

## OpenAPI docs

Docs are available at `/docs`, `/redoc`, and `/openapi.json` when `COUNTRY_COMPARE_API_ENABLE_DOCS=true`. Disable them in production if the API is exposed beyond a trusted network.
