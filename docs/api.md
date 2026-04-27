# Country Compare API

Country Compare exposes a read-only FastAPI backend under the package entrypoint:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

The API is intended to support a separate Streamlit UI container while preserving the existing service/domain architecture.

The API is a transport adapter. Business logic remains in:

```text
country_compare.services
country_compare.comparison
country_compare.prediction
country_compare.scoring
country_compare.data
country_compare.config
```

## Base URL

Local development:

```text
http://localhost:8000
```

Docker Compose backend service URL from the UI container:

```text
http://backend:8000
```

## Versioning

Operational endpoints are unversioned:

```text
GET /health
GET /ready
```

Business endpoints use:

```text
/api/v1
```

## Read-only v0.1 boundary

Allowed:

- metadata reads
- readiness validation
- single-metric comparison
- multi-metric comparison
- profile scoring
- single-metric prediction
- prediction backtesting
- predicted single-metric comparison
- predicted profile comparison

Deferred:

- config editing
- scoring profile editing
- dataset refresh
- ingestion runs
- pipeline execution
- server-side persistent export creation
- authentication/authorization

Do not add write endpoints in v0.1, including:

```text
POST /api/v1/ingestion/run
POST /api/v1/data/refresh
POST /api/v1/config/metrics
POST /api/v1/config/scoring-profiles
PUT  /api/v1/...
DELETE /api/v1/...
```

## Health and readiness

### `GET /health`

Process-level liveness.

This endpoint should not load the dataset or validate config.

Example:

```bash
curl http://localhost:8000/health
```

Example response:

```json
{
  "status": "ok",
  "service": "country-compare-api",
  "version": "0.1.0"
}
```

### `GET /ready`

Traffic-readiness check.

This endpoint validates:

1. the processed dataset exists
2. config validation passes against the current dataset

Example:

```bash
curl http://localhost:8000/ready
```

Ready response:

```json
{
  "status": "ready",
  "dataset": {
    "exists": true
  },
  "config": {
    "valid": true,
    "validated_against_dataset": true
  },
  "warnings": []
}
```

Not-ready response returns HTTP `503`:

```json
{
  "status": "not_ready",
  "dataset": {
    "exists": false
  },
  "config": {
    "valid": false,
    "validated_against_dataset": true
  },
  "warnings": [
    "No dataset is currently available."
  ]
}
```

## Metadata endpoints

Metadata endpoints support UI selector state.

### `GET /api/v1/metadata/dataset`

Returns processed dataset summary.

Example:

```bash
curl http://localhost:8000/api/v1/metadata/dataset
```

Example response:

```json
{
  "exists": true,
  "backend": "parquet",
  "dataset_path": "data/processed/metrics.parquet",
  "row_count": 152260,
  "country_count": 215,
  "metric_count": 21,
  "year_min": 1960,
  "year_max": 2024,
  "available_columns": [
    "country_code",
    "country_name",
    "metric_id",
    "metric_name",
    "value",
    "year"
  ],
  "categories": []
}
```

### `GET /api/v1/metadata/countries`

Returns available country options.

Example:

```bash
curl http://localhost:8000/api/v1/metadata/countries
```

Example response:

```json
{
  "countries": [
    {
      "code": "ISR",
      "name": "Israel"
    }
  ]
}
```

### `GET /api/v1/metadata/metrics`

Returns available metric options.

Example:

```bash
curl http://localhost:8000/api/v1/metadata/metrics
```

Example response:

```json
{
  "metrics": [
    {
      "metric_id": "gdp_per_capita",
      "display_name": "GDP per capita",
      "category": "economy",
      "unit": "USD"
    }
  ]
}
```

### `GET /api/v1/metadata/years`

Returns available dataset years.

Example:

```bash
curl http://localhost:8000/api/v1/metadata/years
```

Example response:

```json
{
  "years": [1960, 1961, 1962],
  "min_year": 1960,
  "max_year": 2024
}
```

### `GET /api/v1/metadata/profiles`

Returns scoring profile summaries.

Example:

```bash
curl http://localhost:8000/api/v1/metadata/profiles
```

Example response:

```json
{
  "profiles": [
    {
      "profile_name": "economic_outlook",
      "description": "Economic outlook profile",
      "metric_ids": [
        "gdp_per_capita",
        "unemployment_pct"
      ],
      "metric_count": 2,
      "year_strategy": "latest_per_metric",
      "missing_data_policy": "allow_partial"
    }
  ]
}
```

## Comparison endpoints

Comparison endpoints return a common result envelope.

### `POST /api/v1/compare/single-metric`

Runs a single-metric comparison.

Example:

```bash
curl -X POST http://localhost:8000/api/v1/compare/single-metric \
  -H "Content-Type: application/json" \
  -d '{
    "country_codes": ["ISR", "FRA", "USA"],
    "metric_id": "gdp_per_capita",
    "year_strategy": "latest_per_metric"
  }'
```

Request body:

```json
{
  "country_codes": ["ISR", "FRA", "USA"],
  "metric_id": "gdp_per_capita",
  "year_strategy": "latest_per_metric",
  "target_year": null,
  "top_n": null
}
```

Notes:

- `country_codes` must contain at least one country.
- `metric_id` must be a configured metric.
- `year_strategy` defaults to `latest_per_metric`.
- `target_year` is required when `year_strategy` is `target_year`.
- `top_n`, when provided, must be greater than zero.

### `POST /api/v1/compare/multi-metric`

Runs a multi-metric comparison.

Example:

```bash
curl -X POST http://localhost:8000/api/v1/compare/multi-metric \
  -H "Content-Type: application/json" \
  -d '{
    "country_codes": ["ISR", "FRA", "USA"],
    "metric_ids": ["gdp_per_capita", "life_expectancy"],
    "year_strategy": "latest_per_metric"
  }'
```

Request body:

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

Runs weighted profile scoring.

Example:

```bash
curl -X POST http://localhost:8000/api/v1/score/profile \
  -H "Content-Type: application/json" \
  -d '{
    "country_codes": ["ISR", "FRA", "USA"],
    "profile_name": "economic_outlook",
    "year_strategy": "latest_per_metric"
  }'
```

Request body:

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

Prediction endpoints return the same common result envelope.

Supported prediction methods depend on the prediction registry. Current baseline methods include:

```text
last_observed
linear_trend
moving_average
```

### `POST /api/v1/prediction/single-metric`

Forecasts one metric for one or more countries.

Example:

```bash
curl -X POST http://localhost:8000/api/v1/prediction/single-metric \
  -H "Content-Type: application/json" \
  -d '{
    "country_codes": ["ISR", "FRA"],
    "metric_id": "gdp_per_capita",
    "horizon_years": 3,
    "method": "linear_trend",
    "fallback_method": "last_observed",
    "scenario_id": "baseline"
  }'
```

Request body:

```json
{
  "country_codes": ["ISR", "FRA"],
  "metric_id": "gdp_per_capita",
  "horizon_years": 3,
  "method": "linear_trend",
  "fallback_method": "last_observed",
  "history_start_year": null,
  "history_end_year": null,
  "scenario_id": "baseline",
  "include_actuals": true
}
```

Notes:

- `horizon_years` must be greater than zero.
- `country_codes` are normalized and deduplicated.
- `history_start_year` must be less than or equal to `history_end_year` when both are provided.

### `POST /api/v1/prediction/backtest`

Runs a holdout backtest for one country and one metric.

Example:

```bash
curl -X POST http://localhost:8000/api/v1/prediction/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "country_codes": ["ISR"],
    "metric_id": "gdp_per_capita",
    "method": "linear_trend",
    "fallback_method": "last_observed",
    "holdout_years": 3,
    "scenario_id": "baseline"
  }'
```

Request body:

```json
{
  "country_codes": ["ISR"],
  "metric_id": "gdp_per_capita",
  "method": "linear_trend",
  "fallback_method": "last_observed",
  "holdout_years": 3,
  "history_start_year": null,
  "history_end_year": null,
  "scenario_id": "baseline"
}
```

Notes:

- Backtesting currently supports exactly one country code.
- `holdout_years` must be greater than zero.

### `POST /api/v1/prediction/compare/single-metric`

Compares countries using a selected future forecast for one metric.

Example:

```bash
curl -X POST http://localhost:8000/api/v1/prediction/compare/single-metric \
  -H "Content-Type: application/json" \
  -d '{
    "country_codes": ["ISR", "FRA", "USA"],
    "metric_id": "gdp_per_capita",
    "horizon_years": 3,
    "forecast_year": 2027,
    "method": "linear_trend",
    "fallback_method": "last_observed",
    "comparison_options": {
      "top_n": null
    }
  }'
```

Request body:

```json
{
  "country_codes": ["ISR", "FRA", "USA"],
  "metric_id": "gdp_per_capita",
  "horizon_years": 3,
  "forecast_year": 2027,
  "forecast_horizon": null,
  "method": "linear_trend",
  "fallback_method": "last_observed",
  "comparison_options": {
    "top_n": null
  }
}
```

Notes:

- Provide only one of `forecast_year` or `forecast_horizon`.
- If neither is provided, service-level default behavior applies.

### `POST /api/v1/prediction/compare/profile`

Compares countries using forecasted values and a scoring profile.

Example:

```bash
curl -X POST http://localhost:8000/api/v1/prediction/compare/profile \
  -H "Content-Type: application/json" \
  -d '{
    "country_codes": ["ISR", "FRA", "USA"],
    "profile_name": "economic_outlook",
    "horizon_years": 3,
    "forecast_year": 2027,
    "method": "linear_trend",
    "fallback_method": "last_observed",
    "comparison_options": {
      "top_n": null
    }
  }'
```

Request body:

```json
{
  "country_codes": ["ISR", "FRA", "USA"],
  "profile_name": "economic_outlook",
  "horizon_years": 3,
  "forecast_year": 2027,
  "forecast_horizon": null,
  "method": "linear_trend",
  "fallback_method": "last_observed",
  "comparison_options": {
    "top_n": null
  }
}
```

## Common computation response envelope

Comparison, scoring, prediction, and backtesting endpoints return a flexible result envelope.

Example shape:

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
  "tables": {
    "main": {
      "row_count": 3,
      "column_count": 8,
      "columns": [
        "country_code",
        "country_name",
        "metric_id",
        "year",
        "value"
      ],
      "records": [],
      "records_truncated": false
    }
  },
  "charts": {},
  "error": null
}
```

## Table payload

Tables are JSON-safe payloads.

```json
{
  "row_count": 3,
  "column_count": 8,
  "columns": [
    "country_code",
    "country_name",
    "metric_id",
    "year",
    "value"
  ],
  "records": [],
  "records_truncated": false
}
```

Serialization rules:

- pandas missing values become `null`
- NumPy scalar values become Python scalar values
- dates/times become ISO strings
- column order is preserved
- tables may be truncated according to API settings

## Error responses

Schema validation errors return FastAPI validation responses with HTTP `422`.

Application-level computation errors return the common result envelope with:

```json
{
  "ok": false,
  "mode": "single_metric",
  "request": {},
  "summary": {},
  "metadata": {},
  "diagnostics": {},
  "warnings": [],
  "messages": [],
  "tables": {},
  "charts": {},
  "error": {
    "code": "resource_not_found",
    "message": "The requested resource was not found.",
    "details": {
      "title": "Resource not found"
    }
  }
}
```

Common status mappings:

```text
400 Bad Request      invalid selection, validation failure, unsupported method
404 Not Found        missing country, metric, profile, or resource
409 Conflict         invalid dataset/config state
422 Unprocessable    request schema validation error
500 Internal Error   unexpected backend failure
503 Unavailable      readiness failure
```

## API settings

API-specific environment variables:

```text
COUNTRY_COMPARE_API_CORS_ORIGINS
COUNTRY_COMPARE_API_MAX_RECORDS
COUNTRY_COMPARE_API_ENABLE_DOCS
```

UI HTTP mode environment variable:

```text
COUNTRY_COMPARE_API_URL
```

Selection rule:

```text
COUNTRY_COMPARE_API_URL unset -> Streamlit uses local services
COUNTRY_COMPARE_API_URL set   -> Streamlit uses the FastAPI backend over HTTP
```

## Docker Compose

Start the backend and UI:

```bash
docker compose up --build
```

Backend:

```text
http://localhost:8000
```

UI:

```text
http://localhost:8501
```

The UI container calls the backend at:

```text
http://backend:8000
```