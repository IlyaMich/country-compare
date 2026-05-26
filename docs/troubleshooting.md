# Troubleshooting

This guide covers common issues in `v0.1 beta`.

Run commands from the repository root unless noted otherwise.

---

## Import errors after `/src` migration

### Symptom

```text
ModuleNotFoundError: No module named 'country_compare'
```

### Fix

Install the package in editable mode:

```bash
python -m pip install -e ".[dev]"
```

Run commands from the repository root.

Confirm the package imports:

```bash
python -c "import country_compare; print(country_compare.__name__)"
```

---

## Accidental `src.country_compare` imports

### Symptom

Imports work locally in one environment but fail in tests, Docker, or installed-package mode.

### Fix

Search for bad imports:

```bash
git grep "src.country_compare"
```

Replace with:

```python
import country_compare
```

or:

```python
from country_compare import ...
```

Do not import from:

```python
import src.country_compare
```

---

## Streamlit path error

### Symptom

Old command fails:

```bash
python -m streamlit run country_compare/ui/app.py
```

### Fix

Use the `/src` filesystem path:

```bash
python -m streamlit run src/country_compare/ui/app.py
```

Or use the CLI:

```bash
country-compare ui
```

---

## UI unexpectedly uses local mode

### Symptom

The UI does not call the backend.

### Fix

Set:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000
```

Then run:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

PowerShell:

```powershell
$env:COUNTRY_COMPARE_API_URL = "http://localhost:8000"
python -m streamlit run src/country_compare/ui/app.py
```

---

## UI cannot reach backend

### Checks

Confirm backend is running:

```bash
curl http://localhost:8000/health
```

PowerShell:

```powershell
curl.exe http://localhost:8000/health
```

Confirm readiness:

```bash
curl http://localhost:8000/ready
```

PowerShell:

```powershell
curl.exe http://localhost:8000/ready
```

In Docker Compose, the UI should usually use:

```text
COUNTRY_COMPARE_API_URL=http://backend:8000
```

not `localhost`, because `localhost` inside the UI container means the UI container itself.

---

## Backend not ready

### Symptom

`/ready` returns not ready or 503.

### Common causes

- processed dataset missing
- config validation failure
- metric/profile config does not match dataset
- data path/store configuration issue
- processed data was not generated
- mounted Docker path does not contain the expected dataset

### Fix

Run:

```bash
country-compare validate-config
country-compare validate-data
```

Inspect the readiness response body for warnings and details:

```bash
curl http://localhost:8000/ready
```

PowerShell:

```powershell
curl.exe http://localhost:8000/ready
```

---

## API requests fail with 401 or 403

### Symptom

Backend API routes reject requests.

### Cause

`COUNTRY_COMPARE_API_KEY` is set on the backend, but the client is not sending it.

### Fix

Send either:

```text
X-API-Key: <value>
```

or:

```text
Authorization: Bearer <value>
```

If using the Streamlit UI in HTTP-backed mode, set the same `COUNTRY_COMPARE_API_KEY` for the UI process/container.

---

## Docker port conflict

### Symptom

Docker Compose fails to bind ports.

### Common ports

```text
8000  backend
8501  Streamlit UI
8080  optional local LLM service override
```

### Fix

Stop the conflicting process or change Compose port mappings.

PowerShell examples:

```powershell
netstat -ano | findstr :8000
netstat -ano | findstr :8501
netstat -ano | findstr :8080
```

---

## Docker Compose starts backend and UI but not LLM service

### Symptom

`llm-forecast` is not running.

### Cause

The LLM service is profile-gated.

### Fix

Start the `llm` profile:

```bash
docker compose --profile llm up --build
```

For local host-side access to port `8080`, use:

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

---

## `llm_forecast` does not appear in the UI

### Symptom

The `llm_forecast` method is missing or unavailable.

### Checks

Check the LLM service:

```bash
curl http://localhost:8080/ready
curl -H "Authorization: Bearer <token>" http://localhost:8080/v1/capabilities
```

PowerShell:

```powershell
curl.exe http://localhost:8080/ready
curl.exe -H "Authorization: Bearer <token>" http://localhost:8080/v1/capabilities
```

Check backend environment:

```env
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_URL=http://llm-forecast:8080
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=<same-as-LLM_SERVICE_TOKEN>
```

### Common causes

- `COUNTRY_COMPARE_ENABLE_LLM_FORECAST` is not `true`
- `COUNTRY_COMPARE_LLM_SERVICE_URL` is missing or wrong
- `COUNTRY_COMPARE_LLM_SERVICE_TOKEN` is missing
- backend token does not match `LLM_SERVICE_TOKEN`
- `MISTRAL_API_KEY` is missing
- public deployment ZDR gate is not satisfied
- `llm-forecast` profile was not started
- backend started before the LLM service became ready
- `/v1/capabilities` returns 503

### Fix

Start the LLM service and confirm capabilities first.

Then restart the backend so it can re-check availability.

---

## LLM service `/ready` returns 503

### Symptom

```text
GET /ready
```

returns `not_ready`.

### Common causes

- `LLM_SERVICE_TOKEN` is missing
- `MISTRAL_API_KEY` is missing
- `MISTRAL_MODEL` is missing
- unsupported `LLM_PROVIDER`
- unsupported `LLM_DEPLOYMENT_PROFILE`
- public deployment requires ZDR but it is not confirmed

### Fix

Inspect the `issues` array in the response.

Local development example:

```env
LLM_SERVICE_TOKEN=dev-token
LLM_PROVIDER=mistral
MISTRAL_API_KEY=<local-secret>
MISTRAL_MODEL=mistral-large-latest
LLM_DEPLOYMENT_PROFILE=local
LLM_REQUIRE_ZDR=false
MISTRAL_ZDR_CONFIRMED=false
```

Public deployment example:

```env
LLM_DEPLOYMENT_PROFILE=public
LLM_REQUIRE_ZDR=true
MISTRAL_ZDR_CONFIRMED=true
```

---

## LLM service `/v1/capabilities` returns 401 or 403

### Symptom

Capabilities fails even though `/ready` is healthy.

### Cause

Missing or incorrect bearer token.

### Fix

Send:

```text
Authorization: Bearer <LLM_SERVICE_TOKEN>
```

Example:

```bash
curl -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

PowerShell:

```powershell
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

The backend value:

```text
COUNTRY_COMPARE_LLM_SERVICE_TOKEN
```

must match the service value:

```text
LLM_SERVICE_TOKEN
```

---

## LLM service returns provider errors

### Symptom

Forecast adjustment fails with provider-related errors.

### Common causes

- invalid `MISTRAL_API_KEY`
- unsupported `MISTRAL_MODEL`
- provider timeout
- provider rate limit
- provider unavailable
- provider returned invalid JSON
- provider returned output outside the allowed bounds

### Fix

Check service logs:

```bash
docker compose --profile llm logs llm-forecast
```

Confirm configuration:

```env
MISTRAL_API_KEY=<valid-local-secret>
MISTRAL_MODEL=mistral-large-latest
LLM_TIMEOUT_SECONDS=20
LLM_MAX_RETRIES=0
LLM_MAX_OUTPUT_TOKENS=800
```

Provider errors should be safe and should not expose secrets.

---

## LLM forecast request exceeds limits

### Symptom

The service returns a `limit_exceeded` error.

### Common causes

- forecast horizon is too large
- history has too many points
- estimated input payload is too large
- requested adjustment percentage exceeds the service limit
- baseline forecast years do not match allowed years

### Relevant settings

```env
LLM_MAX_HORIZON_YEARS=10
LLM_MAX_HISTORY_POINTS=80
LLM_MAX_INPUT_CHARS=12000
LLM_MAX_ADJUSTMENT_PCT=15.0
```

### Fix

Reduce request size or adjust limits deliberately for the deployment.

Do not raise limits without considering cost and privacy implications.

---

## Secrets appear in logs or responses

### Symptom

A log or API response contains a token, key, authorization header, or raw provider payload.

### This is a bug

Secrets must not appear in:

- API responses
- diagnostics
- logs
- UI output
- exported files
- documentation examples

### Fix

Check redaction and safe metadata logic in:

```text
services/llm_forecast_service/src/llm_forecast_service/privacy.py
services/llm_forecast_service/src/llm_forecast_service/main.py
services/llm_forecast_service/src/llm_forecast_service/providers/mistral.py
src/country_compare/prediction/llm/remote_client.py
```

Set:

```env
LLM_DEBUG_LOG_PAYLOADS=false
```

For public deployments, payload logging should be forced off even if configured true.

---

## Missing charts in HTTP/container mode

### Explanation

HTTP mode receives JSON-safe table payloads, not live Python figure objects. The UI rebuilds charts from returned table data.

Charts require usable columns such as:

```text
country/name label
year
metric/series
value/score/forecast/predicted
```

If the returned result table is not chartable, the UI should preserve the table and show a clear explanation instead of failing.

---

## Duplicate tables or charts

### Expected behavior

The main result table should display once. Extra tables should not duplicate the primary `main` table.

If duplicates appear, inspect:

- UI result panel logic
- HTTP result reconstruction
- presentation adapter behavior
- table key selection

---

## Export controls missing

### Checks

- confirm the result object has presentation/export support
- confirm HTTP presentation adapter is available in HTTP-backed mode
- confirm the result has table data to export
- check browser logs
- check backend logs

---

## Mypy, ruff, or black fail on paths

Use `/src` paths for the main app:

```bash
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
```

Use service-local paths for the LLM service:

```bash
cd services/llm_forecast_service
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
```

---

## Async tests fail with unknown `pytest.mark.asyncio`

### Symptom

```text
async def functions are not natively supported
PytestUnknownMarkWarning: Unknown pytest.mark.asyncio
```

### Cause

The LLM service dev environment is missing `pytest-asyncio`.

### Fix

From the service directory:

```bash
python -m pip install -e ".[dev]"
```

Confirm `pytest-asyncio` is included in:

```text
services/llm_forecast_service/pyproject.toml
```

---

## Docker build fails because `pyproject.toml` is missing

### Symptom

```text
ERROR: Directory '.' is not installable. Neither 'setup.py' nor 'pyproject.toml' found.
```

### Cause

The LLM service Dockerfile copied `src/` but not `pyproject.toml`.

### Fix

The LLM service Dockerfile should copy:

```dockerfile
COPY services/llm_forecast_service/pyproject.toml /app/pyproject.toml
COPY services/llm_forecast_service/README.md /app/README.md
COPY services/llm_forecast_service/src /app/src
```

Then run:

```bash
docker compose --profile llm build llm-forecast
```