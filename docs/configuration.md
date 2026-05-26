# Configuration

Country Compare configuration is split between:

1. repository config files,
2. runtime environment variables,
3. Python defaults under `src/country_compare/settings/`,
4. optional LLM forecast microservice settings.

Configuration should stay explicit and environment-driven. Do not commit real API keys, service tokens, or deployment secrets.

---

## Project config files

Typical repository-level config files:

```text
config/metrics.yaml
config/scoring_profiles.yaml
config/source_manifests/
```

### `config/metrics.yaml`

Defines metric metadata used by comparison, scoring, prediction, API responses, and UI selectors.

Common concepts include:

- metric ID
- display name
- category
- unit
- whether higher values are better
- source name and source URL
- optional notes or grouping metadata

### `config/scoring_profiles.yaml`

Defines weighted scoring profiles.

Common concepts include:

- profile name
- description
- included metric IDs
- metric weights
- year strategy
- missing-data behavior, if configured

### `config/source_manifests/`

Defines source acquisition and processing manifests for generating canonical processed data.

The application should normally consume the processed canonical dataset rather than raw source files directly.

---

## Data and store settings

The processed dataset is normally loaded through the configured store backend.

Common environment variables:

```env
COUNTRY_COMPARE_STORE_BACKEND=parquet
COUNTRY_COMPARE_STORE_PATH=data/processed/metrics.parquet
COUNTRY_COMPARE_METRICS_CONFIG=config/metrics.yaml
COUNTRY_COMPARE_SCORING_CONFIG=config/scoring_profiles.yaml
```

In Docker Compose, these paths are usually container paths:

```env
COUNTRY_COMPARE_STORE_PATH=/app/data/processed/metrics.parquet
COUNTRY_COMPARE_METRICS_CONFIG=/app/config/metrics.yaml
COUNTRY_COMPARE_SCORING_CONFIG=/app/config/scoring_profiles.yaml
```

---

## Streamlit client mode

### `COUNTRY_COMPARE_API_URL`

Controls whether Streamlit uses local services or the HTTP backend.

Unset:

```text
Streamlit uses local in-process services.
```

Set:

```text
Streamlit uses the HTTP client and calls the configured FastAPI backend.
```

Example:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

PowerShell example:

```powershell
$env:COUNTRY_COMPARE_API_URL = "http://localhost:8000"
python -m streamlit run src/country_compare/ui/app.py
```

In Docker Compose, the UI container should normally use:

```env
COUNTRY_COMPARE_API_URL=http://backend:8000
```

Do not use `localhost` from inside the UI container to reach the backend container.

---

## Backend API settings

The FastAPI backend is read-only in v0.1 beta.

Common API environment variables:

```env
COUNTRY_COMPARE_API_CORS_ORIGINS=http://localhost:8501
COUNTRY_COMPARE_API_MAX_RECORDS=500
COUNTRY_COMPARE_API_ENABLE_DOCS=true
COUNTRY_COMPARE_API_KEY=
COUNTRY_COMPARE_API_LOG_LEVEL=INFO
```

### `COUNTRY_COMPARE_API_CORS_ORIGINS`

Comma-separated list of allowed CORS origins.

Example:

```env
COUNTRY_COMPARE_API_CORS_ORIGINS=http://localhost:8501,https://example.com
```

When unset, the backend should use safe local defaults. Set this deliberately for deployed environments.

### `COUNTRY_COMPARE_API_MAX_RECORDS`

Maximum number of records serialized in table payloads returned by API endpoints.

Large tables may be truncated in JSON responses while preserving row-count metadata.

### `COUNTRY_COMPARE_API_ENABLE_DOCS`

Controls whether generated FastAPI documentation is enabled.

Useful values:

```env
COUNTRY_COMPARE_API_ENABLE_DOCS=true
COUNTRY_COMPARE_API_ENABLE_DOCS=false
```

### `COUNTRY_COMPARE_API_KEY`

Optional shared API key for protected backend routes.

When set, clients must send one of:

```text
X-API-Key: <value>
Authorization: Bearer <value>
```

`/health` remains public for liveness checks.

If the Streamlit UI calls the backend in HTTP mode, configure the same value for the UI process/container.

---

## API input limits

The backend can enforce request-size limits for API workflows.

Common environment variables:

```env
COUNTRY_COMPARE_API_MAX_COUNTRIES=50
COUNTRY_COMPARE_API_MAX_METRICS=50
COUNTRY_COMPARE_API_MAX_HORIZON_YEARS=10
COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS=10
COUNTRY_COMPARE_API_MAX_TOP_N=100
COUNTRY_COMPARE_API_MAX_RECORDS=500
```

These settings protect the backend from overly large comparison, prediction, scoring, and serialization requests.

---

## Prediction defaults

Application prediction defaults live under:

```text
src/country_compare/settings/defaults.py
src/country_compare/settings/app_settings.py
```

Typical defaults include:

- default prediction method
- default fallback method
- maximum forecast horizon
- maximum backtest holdout years
- default forecast horizon
- default holdout years
- optional LLM forecast limits

Prediction outputs should be treated as baseline statistical projections, not guarantees.

---

## Optional backend LLM forecast integration

The `llm_forecast` method is optional and disabled by default.

The main backend does not call Mistral directly. It calls the private `llm-forecast` microservice over HTTP.

Backend-side LLM environment variables:

```env
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=false
COUNTRY_COMPARE_LLM_PROVIDER=mistral
COUNTRY_COMPARE_LLM_MODEL=mistral-large-latest
COUNTRY_COMPARE_LLM_SERVICE_URL=http://llm-forecast:8080
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=
COUNTRY_COMPARE_LLM_SERVICE_TIMEOUT_SECONDS=25
COUNTRY_COMPARE_LLM_MAX_SERIES_PER_REQUEST=3
COUNTRY_COMPARE_LLM_BASELINE_METHOD=holt_linear
COUNTRY_COMPARE_LLM_MAX_HISTORY_POINTS=40
COUNTRY_COMPARE_LLM_MAX_ADJUSTMENT_PCT=20.0
```

### `COUNTRY_COMPARE_ENABLE_LLM_FORECAST`

Controls whether the backend should attempt to expose `llm_forecast`.

Default:

```env
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=false
```

Set to `true` only when the private LLM service is configured and reachable.

### `COUNTRY_COMPARE_LLM_SERVICE_URL`

URL used by the backend to call the private LLM service.

In Docker Compose:

```env
COUNTRY_COMPARE_LLM_SERVICE_URL=http://llm-forecast:8080
```

For local host-side development:

```env
COUNTRY_COMPARE_LLM_SERVICE_URL=http://localhost:8080
```

### `COUNTRY_COMPARE_LLM_SERVICE_TOKEN`

Shared token used by the backend when calling the LLM service.

This must match the LLM service’s `LLM_SERVICE_TOKEN`.

Do not commit real values.

### Availability behavior

`llm_forecast` should appear only when all of the following are true:

1. `COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true`
2. `COUNTRY_COMPARE_LLM_SERVICE_URL` is configured
3. `COUNTRY_COMPARE_LLM_SERVICE_TOKEN` is configured
4. the LLM service `/v1/capabilities` endpoint succeeds
5. the LLM service reports bounded-adjustment and structured-output support

If the capability check fails, the method should be hidden or unavailable.

---

## Private LLM forecast service settings

The LLM forecast service lives under:

```text
services/llm_forecast_service/
```

It is an independently installable FastAPI microservice.

Service-side environment variables:

```env
LLM_PROVIDER=mistral
LLM_SERVICE_TOKEN=
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-large-latest

LLM_DEPLOYMENT_PROFILE=local
LLM_REQUIRE_ZDR=false
MISTRAL_ZDR_CONFIRMED=false

LLM_TIMEOUT_SECONDS=20
LLM_MAX_RETRIES=0
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

### Required local variables

For local development with the real provider:

```env
LLM_SERVICE_TOKEN=dev-token
LLM_PROVIDER=mistral
MISTRAL_API_KEY=<local-secret>
MISTRAL_MODEL=mistral-large-latest
LLM_DEPLOYMENT_PROFILE=local
```

### Required public deployment variables

For public deployment:

```env
LLM_DEPLOYMENT_PROFILE=public
LLM_REQUIRE_ZDR=true
MISTRAL_ZDR_CONFIRMED=true
```

Public deployments fail readiness unless ZDR is required and confirmed.

### Cost and request limits

The LLM service rejects requests before calling the provider when configured limits are exceeded.

Important limits:

```env
LLM_MAX_SERIES_PER_REQUEST=3
LLM_MAX_HORIZON_YEARS=10
LLM_MAX_HISTORY_POINTS=80
LLM_MAX_INPUT_CHARS=12000
LLM_MAX_OUTPUT_TOKENS=800
LLM_MAX_ADJUSTMENT_PCT=15.0
LLM_MAX_RETRIES=0
```

For this version, LLM forecast requests are one country/metric series at a time.

---

## Docker Compose environment

Default Compose should run only:

```text
backend
ui
```

The LLM service should be profile-gated:

```bash
docker compose --profile llm up --build
```

For local host-side testing of the LLM service port, use the optional override:

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

The default `docker-compose.yml` should not publish the LLM service port publicly.

---

## UI labels and text

Stable UI labels and reusable user-facing text should live in UI text/label modules where appropriate, such as:

```text
src/country_compare/ui/text.py
src/country_compare/ui/navigation.py
```

One-off explanatory copy can remain local to the relevant UI component.

---

## Config validation

Before running beta workflows, validate configuration and data:

```bash
country-compare validate-config
country-compare validate-data
```

The backend readiness endpoint validates service readiness:

```text
http://localhost:8000/ready
```

The optional LLM service readiness endpoint validates provider configuration and public deployment gates:

```text
http://localhost:8080/ready
```

---

## Secret handling

Never commit real values for:

```text
MISTRAL_API_KEY
LLM_SERVICE_TOKEN
COUNTRY_COMPARE_LLM_SERVICE_TOKEN
COUNTRY_COMPARE_API_KEY
```

Secrets must not appear in API responses, diagnostics, logs, README examples, docs, screenshots, or committed `.env` files.

Use local untracked `.env` files or deployment secret stores.