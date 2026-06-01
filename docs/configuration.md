# Configuration

Country Compare has three configuration areas:

1. project/domain configuration under `config/`;
2. API adapter settings under `country_compare.api.settings.ApiSettings` and `COUNTRY_COMPARE_API_*` variables;
3. optional LLM forecast service settings for the private microservice and backend integration.

## Project and domain config

The `config/` directory contains metric metadata, scoring profiles, source manifests, and demo configuration. Domain config should be validated after every change:

```bash
country-compare validate-config
```

Data changes should also validate the processed dataset:

```bash
country-compare validate-data
```

Keep config and pipeline concerns outside the API and UI layers. New data source manifests belong under `config/source_manifests/`; acquisition/processing code belongs in pipeline modules.

## UI client mode

The UI chooses its client mode from `COUNTRY_COMPARE_API_URL`:

```text
COUNTRY_COMPARE_API_URL unset -> local in-process client
COUNTRY_COMPARE_API_URL set   -> HTTP-backed client
```

If the backend has `COUNTRY_COMPARE_API_KEY`, set the same key in the UI process.

## API settings

These variables configure only the FastAPI adapter.

| Variable | Purpose | Default / notes |
| --- | --- | --- |
| `COUNTRY_COMPARE_API_CORS_ORIGINS` | Comma-separated allowed CORS origins. | Usually includes `http://localhost:8501` locally. |
| `COUNTRY_COMPARE_API_MAX_RECORDS` | Max records serialized per table payload. | Positive integer; default commonly `500`. |
| `COUNTRY_COMPARE_API_MAX_COUNTRIES` | Max countries per request. | Positive integer; default commonly `50`. |
| `COUNTRY_COMPARE_API_MAX_METRICS` | Max metrics per request. | Positive integer; default commonly `50`. |
| `COUNTRY_COMPARE_API_MAX_HORIZON_YEARS` | Max prediction horizon. | Positive integer; default commonly `10`. |
| `COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS` | Max backtest holdout years. | Positive integer; default commonly `10`. |
| `COUNTRY_COMPARE_API_MAX_TOP_N` | Max `top_n` result limit. | Positive integer; default commonly `100`. |
| `COUNTRY_COMPARE_API_ENABLE_DOCS` | Enables `/docs`, `/redoc`, `/openapi.json`. | Boolean; disable for exposed production deployments. |
| `COUNTRY_COMPARE_API_KEY` | Optional bearer token for protected endpoints. | Empty/unset disables API-key enforcement. |
| `COUNTRY_COMPARE_API_LOG_LEVEL` | API log level. | Usually `INFO`. |

Parsing rules:

- positive integer variables must parse as integers and be greater than zero;
- booleans accept common forms such as `1`, `true`, `yes`, `y`, `on`, `0`, `false`, `no`, `n`, `off`;
- CSV values are comma-separated and stripped;
- empty optional variables are treated as unset.

## Operational logging

The API creates structured access logs with request id, method, path, status code, and duration. All responses include `X-Request-ID`. Unexpected exceptions are logged server-side with stack traces while client responses remain sanitized.

## Optional LLM forecast backend settings

The backend only exposes `llm_forecast` when all gates pass:

- feature flag enabled;
- service URL and token configured;
- private service reachable;
- `/v1/capabilities` succeeds;
- service reports structured-output support;
- service reports bounded-adjustment support.

Common backend variables:

```text
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=<shared-token>
```

The Compose/local files may set the backend service URL internally. Use the project `.env.example` and Compose overrides as the source of truth for environment names in the deployment target.

## LLM service provider settings

Common local values for the private service:

```text
MISTRAL_API_KEY=<secret>
MISTRAL_MODEL=mistral-large-latest
```

Never commit provider keys, bearer tokens, or real production secrets. Do not log secrets or include them in tests, UI messages, or API responses.

## Example local `.env` sketch

```text
COUNTRY_COMPARE_API_CORS_ORIGINS=http://localhost:8501
COUNTRY_COMPARE_API_MAX_RECORDS=500
COUNTRY_COMPARE_API_MAX_COUNTRIES=50
COUNTRY_COMPARE_API_MAX_METRICS=50
COUNTRY_COMPARE_API_MAX_HORIZON_YEARS=10
COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS=10
COUNTRY_COMPARE_API_MAX_TOP_N=100
COUNTRY_COMPARE_API_ENABLE_DOCS=true
COUNTRY_COMPARE_API_KEY=
COUNTRY_COMPARE_API_LOG_LEVEL=INFO

COUNTRY_COMPARE_API_URL=http://localhost:8000

COUNTRY_COMPARE_ENABLE_LLM_FORECAST=false
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-large-latest
```
