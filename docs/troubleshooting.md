# Troubleshooting

## UI cannot connect to backend

Check `COUNTRY_COMPARE_API_URL`:

```bash
echo $COUNTRY_COMPARE_API_URL
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

In Docker Compose, the UI should usually use `http://backend:8000`, not `http://localhost:8000`, because `localhost` inside the UI container refers to the UI container itself.

## Backend `/ready` returns 503

`/health` is liveness only; `/ready` validates traffic readiness. Common causes:

- processed dataset is missing;
- dataset schema is invalid;
- dataset manifest/checksum is invalid;
- config validation fails;
- scoring profile references unknown metrics;
- data contract changed without updating config/tests.

Run:

```bash
country-compare validate-config
country-compare validate-data
```

## API returns 401 or 403

The backend may have `COUNTRY_COMPARE_API_KEY` set. Supply the bearer token:

```bash
curl -H "Authorization: Bearer $COUNTRY_COMPARE_API_KEY" http://localhost:8000/api/v1/metadata/dataset
```

Set the same key in the UI process when using HTTP mode.

## API docs are missing

`/docs`, `/redoc`, and `/openapi.json` are disabled when `COUNTRY_COMPARE_API_ENABLE_DOCS=false`. This is recommended for exposed production deployments but inconvenient locally.

## Result tables are truncated

Increase `COUNTRY_COMPARE_API_MAX_RECORDS` if appropriate. Keep production limits conservative to avoid very large responses.

## Prediction request fails due limits

Check:

- `COUNTRY_COMPARE_API_MAX_HORIZON_YEARS`;
- `COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS`;
- `COUNTRY_COMPARE_API_MAX_COUNTRIES`;
- `COUNTRY_COMPARE_API_MAX_METRICS`;
- `COUNTRY_COMPARE_API_MAX_TOP_N`.

## `llm_forecast` does not appear

Check:

```bash
curl http://localhost:8000/ready/llm
curl http://localhost:8000/api/v1/metadata/prediction-methods
```

Common causes:

- backend feature flag is off;
- service URL/token missing;
- private LLM service not running;
- token mismatch;
- missing provider API key;
- `/v1/capabilities` response does not report structured output and bounded adjustment support;
- UI is running in a mode that does not see the backend’s method metadata.

## Docker smoke test times out

Inspect backend logs first. Increasing wait time may hide real readiness failures. Typical causes are missing data, bad config, failed imports, or readiness validation errors.

## Data correctness tests fail

Read the fixture that failed:

- golden values: update only when a trusted reference has intentionally changed;
- source alignment: update when a metric deliberately moved source family;
- unit/scale: fix scale errors before relaxing rules;
- plausibility: expand ranges only after confirming the value is valid;
- missingness/staleness: check data coverage before changing thresholds.

## Streamlit charts fail in HTTP mode

The API should return JSON-safe table/chart-ready payloads, not live Python objects. Rebuild charts from records in the UI using Streamlit-native chart functions.
