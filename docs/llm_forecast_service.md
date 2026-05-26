# LLM Forecast Service

The LLM forecast service is an optional private FastAPI microservice used by Country Compare to call an external LLM provider for bounded forecast adjustments.

It is experimental. It does not replace deterministic forecasting methods.

The main backend remains responsible for prediction orchestration, validation, fallback behavior, and user-facing API/UI behavior. The LLM service is only a provider boundary for one country/metric series at a time.

---

## Status

Current intended provider:

```text
Mistral
```

Current service location:

```text
services/llm_forecast_service/
```

Current service package:

```text
llm_forecast_service
```

Current default service port:

```text
8080
```

---

## Architecture

```text
Streamlit UI
  ↓
Country Compare backend
  ↓ RemoteLLMForecastClient
llm-forecast service
  ↓
Mistral
```

Important boundaries:

- Streamlit never receives Mistral credentials.
- The main backend does not call Mistral directly.
- The LLM service does not import `country_compare`.
- The main backend talks to the LLM service over HTTP.
- The LLM service is private and should not be publicly exposed.
- The backend should expose `llm_forecast` only after a successful capability check.

---

## Runtime endpoints

### Public liveness

```text
GET /health
```

Purpose:

```text
Process-level liveness.
```

Expected healthy response:

```json
{
  "status": "ok",
  "service": "llm-forecast-service"
}
```

This endpoint should not require provider readiness.

---

### Readiness

```text
GET /ready
```

Purpose:

```text
Configuration and deployment readiness.
```

This endpoint checks:

- provider is supported
- service token is configured
- Mistral API key is configured
- Mistral model is configured
- public deployment ZDR gate is satisfied
- debug payload logging is disabled for public deployments

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

Example not-ready response:

```json
{
  "status": "not_ready",
  "provider": "mistral",
  "model": "mistral-large-latest",
  "deployment_profile": "public",
  "zdr_required": true,
  "zdr_confirmed": false,
  "debug_payload_logging_enabled": false,
  "issues": [
    "MISTRAL_ZDR_CONFIRMED must be true for public deployments"
  ]
}
```

---

### Capabilities

```text
GET /v1/capabilities
```

Requires:

```text
Authorization: Bearer <LLM_SERVICE_TOKEN>
```

Purpose:

```text
Allows the main backend to decide whether llm_forecast should be exposed.
```

Example response:

```json
{
  "provider": "mistral",
  "model": "mistral-large-latest",
  "supports_structured_output": true,
  "supports_bounded_adjustment": true,
  "max_series_per_request": 3,
  "max_horizon_years": 10,
  "max_history_points": 80,
  "max_input_chars": 12000,
  "max_output_tokens": 800,
  "one_call_per_series": true,
  "zdr_required": false,
  "zdr_confirmed": false,
  "deployment_profile": "local"
}
```

If the service is not ready, this endpoint returns `503`.

---

### Forecast adjustment

```text
POST /v1/forecast/adjust
```

Requires:

```text
Authorization: Bearer <LLM_SERVICE_TOKEN>
```

Purpose:

```text
Return a bounded adjusted forecast for exactly one country/metric series.
```

The service validates:

- request shape
- history length
- horizon length
- allowed years
- input character estimate
- requested adjustment limit
- provider output schema
- provider output years
- provider output finite numeric values
- provider output maximum adjustment versus baseline

The backend should validate again and fall back to deterministic baseline behavior when the remote call fails.

---

## Data sent to the provider

The LLM service sends only the minimum series-level payload needed for bounded adjustment.

Allowed provider input:

- one country code
- one country name
- one metric ID
- one metric name
- metric unit
- historical values for that one series
- baseline forecast values for that one series
- allowed forecast years
- maximum adjustment constraint
- prompt version

---

## Data not sent to the provider

The service must not send:

- full datasets
- all countries
- all metrics
- user identity
- browser/session identity
- service tokens
- Mistral API key
- backend API key
- local file paths
- raw stack traces
- deployment secrets
- unrelated config files
- raw provider credentials
- unredacted diagnostic payloads

---

## Local development

From the service directory:

```powershell
cd .\services\llm_forecast_service
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
```

Run the service locally:

```powershell
$env:LLM_SERVICE_TOKEN = "dev-token"
$env:LLM_PROVIDER = "mistral"
$env:MISTRAL_API_KEY = "<local-secret>"
$env:MISTRAL_MODEL = "mistral-large-latest"
$env:LLM_DEPLOYMENT_PROFILE = "local"
$env:LLM_REQUIRE_ZDR = "false"
$env:MISTRAL_ZDR_CONFIRMED = "false"

python -m uvicorn llm_forecast_service.main:app --host 0.0.0.0 --port 8080
```

Check from another terminal:

```powershell
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/ready
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

---

## Docker Compose setup

The default Compose stack should run only:

```text
backend
ui
```

Start the default stack:

```bash
docker compose up --build
```

Start with the optional LLM profile:

```bash
docker compose --profile llm up --build
```

For local host-side testing of `localhost:8080`, use the local override:

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

The default `docker-compose.yml` should use `expose`, not `ports`, for the LLM service:

```yaml
expose:
  - "8080"
```

Only the local override should publish:

```yaml
ports:
  - "8080:8080"
```

---

## Backend integration variables

The backend uses these variables:

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

`COUNTRY_COMPARE_ENABLE_LLM_FORECAST` should default to `false`.

`COUNTRY_COMPARE_LLM_SERVICE_TOKEN` must match the service-side `LLM_SERVICE_TOKEN`.

---

## Service variables

The LLM service uses these variables:

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

Do not commit real values for:

```text
MISTRAL_API_KEY
LLM_SERVICE_TOKEN
COUNTRY_COMPARE_LLM_SERVICE_TOKEN
```

---

## Public deployment ZDR gate

For public deployments, configure:

```env
LLM_DEPLOYMENT_PROFILE=public
LLM_REQUIRE_ZDR=true
MISTRAL_ZDR_CONFIRMED=true
```

If ZDR is not confirmed:

- `/ready` returns `503`
- `/v1/capabilities` returns `503`
- the main backend should not expose `llm_forecast`

`MISTRAL_ZDR_CONFIRMED=true` is an operator attestation that provider privacy and zero-data-retention requirements have been reviewed and approved.

---

## Cost controls

The service rejects requests above configured limits before calling the provider.

Important variables:

```env
LLM_MAX_SERIES_PER_REQUEST=3
LLM_MAX_HORIZON_YEARS=10
LLM_MAX_HISTORY_POINTS=80
LLM_MAX_INPUT_CHARS=12000
LLM_MAX_OUTPUT_TOKENS=800
LLM_MAX_ADJUSTMENT_PCT=15.0
LLM_MAX_RETRIES=0
```

Design constraints:

- one request is one country/metric series
- one request makes at most one provider call, except configured retries
- provider output is validated before returning
- the main backend validates again
- the main backend should fall back to deterministic baseline behavior on remote failure

---

## Privacy and diagnostics

Diagnostics must be safe by default.

Allowed metadata examples:

```text
provider
model
prompt_version
llm_calls
latency_ms
deployment_profile
zdr_required
zdr_confirmed
max_horizon_years
max_history_points
max_input_chars
max_output_tokens
max_adjustment_pct
```

Never expose:

```text
MISTRAL_API_KEY
LLM_SERVICE_TOKEN
COUNTRY_COMPARE_LLM_SERVICE_TOKEN
Authorization header
raw provider response body
raw prompt content in public deployment
stack traces in API responses
```

Payload logging must be disabled for public deployments even if `LLM_DEBUG_LOG_PAYLOADS=true`.

---

## Manual QA checklist

### 1. Service tests

```powershell
cd .\services\llm_forecast_service
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
cd ..\..
```

Expected:

```text
All checks pass.
No secrets are printed.
```

### 2. Default Compose without LLM

```powershell
docker compose up --build
```

Check:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/ready
```

Open:

```text
http://localhost:8501
```

Expected:

```text
backend starts
ui starts
llm-forecast does not start
normal prediction methods still work
llm_forecast is hidden or unavailable
```

Stop:

```powershell
docker compose down --volumes --remove-orphans
```

### 3. LLM service missing-key readiness gate

```powershell
$env:COUNTRY_COMPARE_LLM_SERVICE_TOKEN = "dev-token"
Remove-Item Env:MISTRAL_API_KEY -ErrorAction SilentlyContinue

docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build llm-forecast
```

In another terminal:

```powershell
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/ready
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

Expected:

```text
/health returns ok
/ready returns 503 not_ready
/v1/capabilities returns 503 service_not_ready
responses do not contain service token or provider API key
```

### 4. Auth checks

```powershell
curl.exe http://localhost:8080/v1/capabilities
curl.exe -H "Authorization: Bearer wrong-token" http://localhost:8080/v1/capabilities
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

Expected:

```text
missing auth fails
wrong token fails
correct token succeeds only when service is ready
```

### 5. Public ZDR gate

```powershell
$env:COUNTRY_COMPARE_LLM_SERVICE_TOKEN = "dev-token"
$env:MISTRAL_API_KEY = "<real-or-test-key>"
$env:LLM_DEPLOYMENT_PROFILE = "public"
$env:LLM_REQUIRE_ZDR = "true"
$env:MISTRAL_ZDR_CONFIRMED = "false"

docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build llm-forecast
```

Check:

```powershell
curl.exe http://localhost:8080/ready
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

Expected:

```text
/ready returns 503
/v1/capabilities returns 503
issue mentions MISTRAL_ZDR_CONFIRMED
```

Set:

```powershell
$env:MISTRAL_ZDR_CONFIRMED = "true"
```

Restart and verify readiness succeeds.

### 6. Full local LLM smoke test

Create a local untracked `.env` with:

```env
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=dev-token
MISTRAL_API_KEY=<real-local-secret>
MISTRAL_MODEL=mistral-large-latest
LLM_DEPLOYMENT_PROFILE=local
LLM_REQUIRE_ZDR=false
MISTRAL_ZDR_CONFIRMED=false
```

Run:

```powershell
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

Verify:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/ready
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/ready
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

Open:

```text
http://localhost:8501
```

Expected:

```text
backend ready
ui ready
llm-forecast ready
llm_forecast appears as an experimental prediction method
single-series forecast works
warnings/diagnostics clearly mark it experimental
forecast respects bounded adjustment limits
```

### 7. Fallback behavior

Break the LLM service intentionally:

```powershell
$env:MISTRAL_API_KEY = "invalid-key"
```

Restart the stack and run an LLM forecast from the UI or API.

Expected:

```text
backend does not crash
prediction returns deterministic baseline fallback where designed
diagnostics include fallback information
no provider secret appears in API response, UI, or logs
```

### 8. Log/privacy check

```powershell
docker compose --profile llm logs backend
docker compose --profile llm logs llm-forecast
```

Expected:

```text
no MISTRAL_API_KEY
no COUNTRY_COMPARE_LLM_SERVICE_TOKEN
no LLM_SERVICE_TOKEN
no Authorization header
no raw provider response body containing sensitive details
```

### 9. Cleanup

```powershell
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml down --volumes --remove-orphans

Remove-Item Env:MISTRAL_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:COUNTRY_COMPARE_LLM_SERVICE_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:LLM_DEPLOYMENT_PROFILE -ErrorAction SilentlyContinue
Remove-Item Env:LLM_REQUIRE_ZDR -ErrorAction SilentlyContinue
Remove-Item Env:MISTRAL_ZDR_CONFIRMED -ErrorAction SilentlyContinue
```

---

## Troubleshooting

### `llm_forecast` does not appear

Check:

```powershell
curl.exe http://localhost:8080/ready
curl.exe -H "Authorization: Bearer <token>" http://localhost:8080/v1/capabilities
```

Common causes:

- `COUNTRY_COMPARE_ENABLE_LLM_FORECAST` is not `true`
- `COUNTRY_COMPARE_LLM_SERVICE_URL` is missing or wrong
- backend token does not match `LLM_SERVICE_TOKEN`
- `MISTRAL_API_KEY` is missing
- public deployment ZDR gate is not satisfied
- the `llm` Compose profile was not started
- the backend was started before the LLM service became ready

### `/v1/capabilities` returns 401 or 403

Check that the request includes:

```text
Authorization: Bearer <LLM_SERVICE_TOKEN>
```

The backend value:

```text
COUNTRY_COMPARE_LLM_SERVICE_TOKEN
```

must match the service value:

```text
LLM_SERVICE_TOKEN
```

### `/ready` returns not ready

Inspect the `issues` array in the response.

Common causes:

- missing `LLM_SERVICE_TOKEN`
- missing `MISTRAL_API_KEY`
- missing `MISTRAL_MODEL`
- unsupported provider
- public deployment without ZDR confirmation

### Provider request fails

Check:

- `MISTRAL_API_KEY` is valid
- `MISTRAL_MODEL` is supported
- network access to the provider works
- rate limits are not exceeded
- request limits are not too strict

The service should return safe errors without leaking secrets.

---

## Related files

```text
services/llm_forecast_service/src/llm_forecast_service/main.py
services/llm_forecast_service/src/llm_forecast_service/settings.py
services/llm_forecast_service/src/llm_forecast_service/providers/mistral.py
services/llm_forecast_service/src/llm_forecast_service/limits.py
services/llm_forecast_service/src/llm_forecast_service/privacy.py
src/country_compare/prediction/llm/remote_client.py
src/country_compare/prediction/llm/forecasters.py
```