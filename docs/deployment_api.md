# Deploying the FastAPI backend

The backend is a read-only API adapter over the Country Compare service/domain core. Deploy it with the processed dataset and validated config already available to the container or runtime.

## Deployment model

```text
client / UI
  -> reverse proxy / ingress
  -> FastAPI backend
  -> country_compare.services
  -> processed dataset + config
```

Optional private LLM runtime:

```text
FastAPI backend
  -> private network + bearer token
  -> llm-forecast service
  -> provider API
```

## Required pre-deployment checks

```bash
country-compare validate-config
country-compare validate-data
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
docker compose build
```

When deploying the LLM service:

```bash
cd services/llm_forecast_service
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
cd ../..
docker compose --profile llm build llm-forecast
```

## Runtime command

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Container deployments can run the same app module with Uvicorn/Gunicorn according to platform standards.

## Environment

Recommended production posture:

```text
COUNTRY_COMPARE_API_ENABLE_DOCS=false
COUNTRY_COMPARE_API_KEY=<strong-token-or-upstream-auth-only>
COUNTRY_COMPARE_API_CORS_ORIGINS=<trusted-ui-origin>
COUNTRY_COMPARE_API_LOG_LEVEL=INFO
COUNTRY_COMPARE_API_MAX_RECORDS=500
COUNTRY_COMPARE_API_MAX_COUNTRIES=50
COUNTRY_COMPARE_API_MAX_METRICS=50
COUNTRY_COMPARE_API_MAX_HORIZON_YEARS=10
COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS=10
COUNTRY_COMPARE_API_MAX_TOP_N=100
```

Use upstream authentication/authorization if exposing the API outside a private environment. `COUNTRY_COMPARE_API_KEY` is a simple bearer-token guard, not a full user auth system.

## Health and readiness

Use `/health` for liveness and `/ready` for traffic readiness.

```bash
curl http://<host>/health
curl http://<host>/ready
```

`/ready` should fail closed if the dataset/config is invalid or missing. Wire load balancers and orchestrators to readiness, not just health.

## Metrics and logs

- `/metrics` exposes operational metrics when enabled.
- All responses include `X-Request-ID`.
- Access logs include request id, method, path, status, and duration.
- Unexpected exceptions should be logged with stack traces server-side and sanitized for clients.

## Data publishing

Do not run ingestion or data refresh through the deployed API. Publish validated processed data artifacts through the project’s data pipeline/release process, then roll out the backend with those artifacts.

## Optional LLM service deployment

The LLM service must remain private and token-protected. Do not publish it directly to the internet.

Backend gates for exposing `llm_forecast`:

- `COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true`;
- service URL/token configured;
- private service reachable;
- `/v1/capabilities` succeeds;
- capabilities include structured output and bounded adjustment support.

Check:

```bash
curl http://<backend>/ready/llm
curl http://<backend>/api/v1/metadata/prediction-methods
```

## Rollback criteria

Rollback or keep traffic disabled when:

- `/ready` returns `503`;
- critical metadata endpoints fail;
- comparison/scoring representative smoke calls fail;
- API error rate or latency spikes after rollout;
- `llm_forecast` appears when the private service is not intended to be enabled;
- secrets are detected in logs or responses.
