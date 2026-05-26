# Country Compare LLM Forecast Service

FastAPI gateway service used by the Country Compare backend to request LLM-assisted forecast adjustments.

The service currently supports Mistral as the LLM provider. It is intentionally small and stateless: the main Country Compare backend owns the application workflow, while this service owns the LLM HTTP boundary, provider calls, response validation, safety limits, and operational readiness.

## Purpose

The service receives a baseline forecast from the Country Compare backend and asks an LLM to return a bounded adjusted forecast.

It is designed to:

- keep provider-specific LLM logic outside the main backend
- validate LLM output before returning it to the backend
- enforce cost and input-size limits
- avoid logging sensitive forecast payloads
- expose lightweight health/readiness endpoints for deployment checks
- support independent deployment as a separate Render service

## Service location

```text
services/llm_forecast_service/
```

Package import name:

```text
llm_forecast_service
```

## Runtime architecture

```text
Country Compare backend
  -> RemoteLLMForecastClient
  -> LLM Forecast Service
  -> Mistral API
```

The Streamlit UI should not call this service directly. The expected path is:

```text
Streamlit UI -> Country Compare backend -> LLM Forecast Service -> Mistral
```

## Endpoints

### `GET /health`

Process-level liveness check.

Does not require authentication.

Example:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "llm-forecast-service"
}
```

### `GET /ready`

Strict readiness check.

Does not call Mistral. It validates service configuration and whether the service is allowed to accept traffic.

Example:

```bash
curl http://localhost:8080/ready
```

Example ready response:

```json
{
  "status": "ready",
  "provider": "mistral",
  "model": "mistral-large-latest",
  "deployment_profile": "local",
  "zdr_required": false,
  "zdr_confirmed": false,
  "debug_payload_logging_enabled": false,
  "issues": []
}
```

### `GET /v1/capabilities`

Authenticated endpoint used by the backend to verify backend-to-LLM-service wiring.

Requires:

```text
Authorization: Bearer <LLM_SERVICE_TOKEN>
```

Example:

```bash
curl \
  --header "Authorization: Bearer dev-token" \
  http://localhost:8080/v1/capabilities
```

### `POST /v1/forecast/adjust`

Authenticated endpoint used by the backend to request an LLM forecast adjustment.

Requires:

```text
Authorization: Bearer <LLM_SERVICE_TOKEN>
```

This endpoint may call Mistral and can incur provider cost.

## Authentication

Business endpoints require a bearer token:

```text
LLM_SERVICE_TOKEN
```

The Country Compare backend must be configured with the same value through:

```text
COUNTRY_COMPARE_LLM_SERVICE_TOKEN
```

Do not commit this token to Git.

## Environment variables

### Required

| Variable | Description |
|---|---|
| `LLM_SERVICE_TOKEN` | Bearer token required by `/v1/*` endpoints. |
| `MISTRAL_API_KEY` | Mistral API key used by the provider adapter. |

### Provider configuration

| Variable | Default | Description |
|---|---:|---|
| `LLM_PROVIDER` | `mistral` | Active LLM provider. |
| `MISTRAL_MODEL` | `mistral-large-latest` | Mistral model name. |
| `LLM_TEMPERATURE` | `0` | Provider temperature. Keep deterministic for forecast adjustment. |
| `LLM_MAX_OUTPUT_TOKENS` | `800` | Maximum output tokens requested from the provider. |

### Runtime and deployment

| Variable | Default | Description |
|---|---:|---|
| `PORT` | `8080` | HTTP port. Render injects this automatically. |
| `LLM_DEPLOYMENT_PROFILE` | `local` | Deployment profile. `public` enables stricter ZDR readiness checks. |
| `LLM_REQUIRE_ZDR` | `false` | Whether zero-data-retention is required. |
| `MISTRAL_ZDR_CONFIRMED` | `false` | Whether the configured Mistral account/model setup has confirmed ZDR. |
| `LLM_LOG_LEVEL` | `INFO` | Python log level. |
| `LLM_DEBUG_LOG_PAYLOADS` | `false` | Debug payload logging. Keep `false` outside local debugging. |

### Request safety limits

| Variable | Default | Description |
|---|---:|---|
| `LLM_MAX_CONCURRENT_REQUESTS` | `1` | Max concurrent provider calls inside the service. |
| `LLM_TIMEOUT_SECONDS` | `20` | Provider request timeout. |
| `LLM_MAX_RETRIES` | `1` | Provider retry count. Keep low to avoid accidental spend. |
| `LLM_MAX_SERIES_PER_REQUEST` | `3` | Maximum series accepted in one request. |
| `LLM_MAX_HORIZON_YEARS` | `10` | Maximum forecast horizon. |
| `LLM_MAX_HISTORY_POINTS` | `80` | Maximum historical points accepted. |
| `LLM_MAX_INPUT_CHARS` | `12000` | Maximum prompt/input size budget. |
| `LLM_MAX_ADJUSTMENT_PCT` | `15.0` | Maximum allowed percentage adjustment from baseline. |

## Local development

From the service directory:

```bash
cd services/llm_forecast_service
python -m pip install -e ".[dev]"
```

Run checks:

```bash
python -m pytest
python -m black --check src tests
python -m ruff check src tests
python -m mypy src
```

Run locally:

```bash
LLM_SERVICE_TOKEN=dev-token \
MISTRAL_API_KEY=<your-mistral-api-key> \
python -m uvicorn llm_forecast_service.main:app --host 0.0.0.0 --port 8080
```

PowerShell:

```powershell
$env:LLM_SERVICE_TOKEN = "dev-token"
$env:MISTRAL_API_KEY = "<your-mistral-api-key>"
python -m uvicorn llm_forecast_service.main:app --host 0.0.0.0 --port 8080
```

Check:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl --header "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

## Docker

Build from the repository root:

```bash
docker build \
  --file services/llm_forecast_service/Dockerfile \
  --tag llm-forecast-service:local \
  .
```

Run:

```bash
docker run --rm \
  --publish 8080:8080 \
  --env PORT=8080 \
  --env LLM_SERVICE_TOKEN=dev-token \
  --env MISTRAL_API_KEY=<your-mistral-api-key> \
  llm-forecast-service:local
```

Check:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/ready
curl --header "Authorization: Bearer dev-token" http://127.0.0.1:8080/v1/capabilities
```

## Docker Compose

The service can be run through the repository Compose setup using the `llm` profile.

From the repository root:

```bash
docker compose --profile llm up --build
```

The service is expected to listen on:

```text
http://localhost:8080
```

## Render deployment

This service is deployed as a separate Render Web Service using the Docker image published to GHCR.

Recommended Render settings:

```text
Service type: Web Service
Runtime: Existing Docker image
Health check path: /health
Instance type: Free for beta/testing
```

Recommended image:

```text
ghcr.io/<github-owner>/country-compare-llm-forecast:<tag>
```

Recommended Render environment variables:

```text
LLM_SERVICE_TOKEN=<strong-random-token>
LLM_PROVIDER=mistral
MISTRAL_API_KEY=<mistral-api-key>
MISTRAL_MODEL=mistral-large-latest

LLM_DEPLOYMENT_PROFILE=local
LLM_REQUIRE_ZDR=false
MISTRAL_ZDR_CONFIRMED=false

LLM_TIMEOUT_SECONDS=20
LLM_MAX_RETRIES=1
LLM_MAX_CONCURRENT_REQUESTS=1

LLM_TEMPERATURE=0
LLM_MAX_OUTPUT_TOKENS=800
LLM_MAX_SERIES_PER_REQUEST=3
LLM_MAX_HORIZON_YEARS=10
LLM_MAX_HISTORY_POINTS=80
LLM_MAX_INPUT_CHARS=12000
LLM_MAX_ADJUSTMENT_PCT=15.0

LLM_LOG_LEVEL=INFO
LLM_DEBUG_LOG_PAYLOADS=false
```

For a public deployment where ZDR is required and confirmed:

```text
LLM_DEPLOYMENT_PROFILE=public
LLM_REQUIRE_ZDR=true
MISTRAL_ZDR_CONFIRMED=true
```

Do not set `MISTRAL_ZDR_CONFIRMED=true` unless it has actually been confirmed for the configured Mistral setup.

## GitHub Actions deployment

The service is deployed by:

```text
.github/workflows/deploy-llm-forecast.yaml
```

The workflow:

1. resolves the GHCR image tag
2. triggers the Render deploy hook with `imgURL`
3. waits for `/health`
4. waits for `/ready`
5. checks authenticated `/v1/capabilities`

Required GitHub environment secrets:

```text
COUNTRY_COMPARE_LLM_DEPLOY_WEBHOOK_URL
COUNTRY_COMPARE_LLM_SERVICE_BASE_URL
COUNTRY_COMPARE_LLM_SERVICE_TOKEN
```

The Mistral API key should stay in Render environment variables. CI does not need the real Mistral API key because smoke checks do not call `/v1/forecast/adjust`.

## Connecting the main backend

The Country Compare backend must be configured with:

```text
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_URL=https://<llm-service>.onrender.com
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=<same value as LLM_SERVICE_TOKEN>
COUNTRY_COMPARE_LLM_SERVICE_TIMEOUT_SECONDS=75
COUNTRY_COMPARE_LLM_MAX_ADJUSTMENT_PCT=15.0
```

Use a longer backend timeout on free Render deployments because the LLM service may cold start.

Backend-to-LLM readiness can be checked through the main backend:

```bash
curl \
  --header "Authorization: Bearer <COUNTRY_COMPARE_API_KEY>" \
  https://<backend-service>.onrender.com/ready/llm
```

## Privacy and logging

The service should not log:

- Mistral API keys
- service bearer tokens
- request payloads
- historical series values
- baseline forecast values
- raw prompts
- raw provider responses

Structured logs may include safe operational metadata such as:

- request id
- country code
- metric id
- horizon years
- provider
- model
- status
- latency
- queue wait
- error code

Keep this disabled outside local debugging:

```text
LLM_DEBUG_LOG_PAYLOADS=false
```

## Retry and cost behavior

Provider retry behavior is intentionally conservative.

The service supports:

- timeout handling
- retry for transient provider request errors
- retry for provider `429` and `5xx`
- exponential backoff with jitter
- `Retry-After` support when sent by the provider

Keep `LLM_MAX_RETRIES` low, usually:

```text
LLM_MAX_RETRIES=1
```

This reduces accidental token spend and keeps UI requests responsive.

## Troubleshooting

### `/health` returns 200 but `/ready` returns 503

The process is running, but configuration is not ready.

Check the `issues` field returned by `/ready`.

Common causes:

- missing `MISTRAL_API_KEY`
- missing `LLM_SERVICE_TOKEN`
- `LLM_DEPLOYMENT_PROFILE=public` without confirmed ZDR flags
- invalid concurrency or limit settings

### `/v1/capabilities` returns `401` or `403`

The `Authorization` header is missing or the token does not match `LLM_SERVICE_TOKEN`.

Expected header:

```text
Authorization: Bearer <LLM_SERVICE_TOKEN>
```

### `/v1/capabilities` returns `service_not_ready`

The service is reachable and authenticated, but readiness failed.

Check:

```bash
curl https://<llm-service>/ready
```

### Render deployment succeeds but workflow smoke fails on `/ready`

The service may still be rolling out or cold starting.

The deployment workflow should poll `/ready` until it returns 200. If it still fails, inspect the readiness response body printed in the workflow logs.

### Forecast requests timeout on first use

On Render Free, the service may cold start after being idle.

Use a longer backend timeout:

```text
COUNTRY_COMPARE_LLM_SERVICE_TIMEOUT_SECONDS=75
```

## Security checklist

Before deploying:

- `MISTRAL_API_KEY` is configured only in Render.
- `LLM_SERVICE_TOKEN` is strong and shared only with the backend and GitHub deployment smoke secrets.
- `LLM_DEBUG_LOG_PAYLOADS=false`.
- `/v1/*` endpoints require bearer authentication.
- concurrency is capped with `LLM_MAX_CONCURRENT_REQUESTS=1` for beta/free deployment.
- provider retries are low with `LLM_MAX_RETRIES=1`.
- readiness checks pass.
- post-deploy workflow smoke checks pass.
