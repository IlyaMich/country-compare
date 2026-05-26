# Manual QA Checklist

This checklist verifies the Country Compare app after adding the optional private LLM forecast service.

Run commands from the repository root unless a step explicitly says otherwise.

The LLM forecast service is optional and should remain disabled by default. It should only become available when the backend flag, service URL, shared token, LLM service readiness, and `/v1/capabilities` check all succeed.

---

## 1. Pre-flight setup

### 1.1 Confirm branch and clean working tree

```powershell
git branch --show-current
git status --short
```

Expected:

```text
Current branch is the intended feature branch.
No unexpected generated files are present.
No real secrets are staged.
```

Generated files that should not be committed:

```text
*.egg-info/
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
```

### 1.2 Confirm secret examples are safe

Check these files manually:

```text
.env.example
docker-compose.yml
docker-compose.llm-local.yml
README.md
docs/configuration.md
docs/llm_forecast_service.md
docs/troubleshooting.md
```

Expected:

```text
No real MISTRAL_API_KEY value.
No real LLM_SERVICE_TOKEN value.
No real COUNTRY_COMPARE_LLM_SERVICE_TOKEN value.
No real COUNTRY_COMPARE_API_KEY value.
Committed examples use blank values or obvious placeholders only.
```

---

## 2. Main app automated checks

Run:

```powershell
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
```

Expected:

```text
All tests pass.
Ruff passes.
Black check passes.
Mypy passes.
No secrets are printed.
```

---

## 3. LLM forecast service automated checks

Run:

```powershell
cd .\services\llm_forecast_service
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
cd ..\..
```

Expected:

```text
All service tests pass.
Ruff passes.
Black check passes.
Mypy passes.
No secrets are printed.
```

---

## 4. Default local Streamlit mode

Make sure HTTP mode is not enabled:

```powershell
Remove-Item Env:COUNTRY_COMPARE_API_URL -ErrorAction SilentlyContinue
country-compare ui
```

Open:

```text
http://localhost:8501
```

Verify:

```text
UI opens.
Comparison workflows load.
Prediction workflows load.
Normal deterministic prediction methods are available.
No backend process is required.
llm_forecast is hidden or unavailable unless explicitly configured.
No secrets appear in the UI.
```

Stop the UI with `Ctrl + C`.

---

## 5. Local backend API mode

Terminal 1:

```powershell
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Terminal 2:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/ready
```

Expected:

```text
/health returns ok.
/ready returns ready or a clear not_ready response with actionable details.
No LLM service is required for normal backend readiness.
```

Start Streamlit in HTTP-backed mode:

```powershell
$env:COUNTRY_COMPARE_API_URL = "http://localhost:8000"
python -m streamlit run src/country_compare/ui/app.py
```

Open:

```text
http://localhost:8501
```

Verify:

```text
UI uses HTTP-backed mode.
Metadata selectors load.
Comparison workflows work.
Prediction workflows work.
Exports still appear where expected.
llm_forecast remains hidden or unavailable unless the LLM service is enabled and ready.
```

Stop both processes with `Ctrl + C`.

---

## 6. Default Docker Compose stack without LLM

Run:

```powershell
docker compose up --build
```

Or, if using Podman with Compose:

```powershell
podman compose -f docker-compose.yml up --build
```

Verify from another terminal:

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
backend starts.
ui starts.
llm-forecast does not start by default.
normal comparison workflows work.
normal prediction workflows work.
llm_forecast is hidden or unavailable.
Port 8080 is not publicly reachable unless the local LLM override file is used.
```

Stop:

```powershell
docker compose down --volumes --remove-orphans
```

Or:

```powershell
podman compose -f docker-compose.yml down --volumes --remove-orphans
```

---

## 7. LLM service image build

Run:

```powershell
docker compose --profile llm build llm-forecast
```

Or:

```powershell
podman compose --profile llm -f docker-compose.yml build llm-forecast
```

Expected:

```text
Image builds successfully.
Dockerfile copies pyproject.toml, README.md, and src/ into the image.
No runtime dependency is missing.
```

---

## 8. LLM service missing-key readiness gate

Run with no Mistral key:

```powershell
$env:COUNTRY_COMPARE_LLM_SERVICE_TOKEN = "dev-token"
Remove-Item Env:MISTRAL_API_KEY -ErrorAction SilentlyContinue

docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build llm-forecast
```

Or:

```powershell
podman compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build llm-forecast
```

In another terminal:

```powershell
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/ready
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

Expected:

```text
/health returns ok.
/ready returns 503 not_ready.
/v1/capabilities returns 503 service_not_ready.
The response mentions missing MISTRAL_API_KEY or another clear readiness issue.
No service token or provider API key appears in responses.
```

Stop:

```powershell
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml down --volumes --remove-orphans
```

---

## 9. LLM service auth checks

Start the LLM service with a valid local config. A real key is not required for auth-only checks if readiness failure is acceptable, but capabilities succeeds only when the service is ready.

```powershell
$env:COUNTRY_COMPARE_LLM_SERVICE_TOKEN = "dev-token"
$env:MISTRAL_API_KEY = "<real-local-secret-or-test-value>"
$env:LLM_DEPLOYMENT_PROFILE = "local"
$env:LLM_REQUIRE_ZDR = "false"
$env:MISTRAL_ZDR_CONFIRMED = "false"

docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build llm-forecast
```

In another terminal:

```powershell
curl.exe http://localhost:8080/v1/capabilities
curl.exe -H "Authorization: Bearer wrong-token" http://localhost:8080/v1/capabilities
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

Expected:

```text
Missing auth fails.
Wrong token fails.
Correct token succeeds only when the service is ready.
Failure responses do not leak configured tokens.
```

---

## 10. Public deployment ZDR gate

Run with public deployment and ZDR not confirmed:

```powershell
$env:COUNTRY_COMPARE_LLM_SERVICE_TOKEN = "dev-token"
$env:MISTRAL_API_KEY = "<real-local-secret-or-test-value>"
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
/ready returns 503.
/v1/capabilities returns 503.
The issue list mentions MISTRAL_ZDR_CONFIRMED.
Debug payload logging is reported as disabled.
No secrets appear in responses.
```

Now set ZDR confirmed:

```powershell
$env:MISTRAL_ZDR_CONFIRMED = "true"
```

Restart the LLM service and re-check:

```powershell
curl.exe http://localhost:8080/ready
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

Expected:

```text
The service becomes ready if all other required config is valid.
Capabilities succeeds with the correct token.
```

---

## 11. Full local LLM Compose smoke test

Create or update a local untracked `.env` file:

```env
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=dev-token
COUNTRY_COMPARE_LLM_SERVICE_URL=http://llm-forecast:8080
COUNTRY_COMPARE_LLM_PROVIDER=mistral
COUNTRY_COMPARE_LLM_MODEL=mistral-large-latest
COUNTRY_COMPARE_LLM_SERVICE_TIMEOUT_SECONDS=25
COUNTRY_COMPARE_LLM_MAX_SERIES_PER_REQUEST=3
COUNTRY_COMPARE_LLM_BASELINE_METHOD=holt_linear
COUNTRY_COMPARE_LLM_MAX_HISTORY_POINTS=40
COUNTRY_COMPARE_LLM_MAX_ADJUSTMENT_PCT=20.0

LLM_PROVIDER=mistral
LLM_SERVICE_TOKEN=dev-token
MISTRAL_API_KEY=<real-local-secret>
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
backend is healthy.
backend is ready or gives only expected non-blocking readiness details.
ui is reachable.
llm-forecast is healthy.
llm-forecast is ready.
/v1/capabilities succeeds.
llm_forecast appears as an experimental prediction method.
A single-series LLM forecast can run.
The UI clearly presents forecast warnings/diagnostics.
The output remains bounded versus the deterministic baseline.
No secrets appear in API responses, UI, or logs.
```

---

## 12. Backend LLM capability gating

With the full LLM profile running and ready, verify method availability through the UI or metadata/catalog endpoint used by the frontend.

Expected:

```text
When COUNTRY_COMPARE_ENABLE_LLM_FORECAST=false, llm_forecast is hidden.
When COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true but service token is missing, llm_forecast is hidden.
When service is not ready, llm_forecast is hidden.
When capabilities succeeds, llm_forecast appears.
```

Suggested checks:

```powershell
# Backend disabled
$env:COUNTRY_COMPARE_ENABLE_LLM_FORECAST = "false"
# restart backend and verify llm_forecast is unavailable

# Backend enabled but bad token
$env:COUNTRY_COMPARE_ENABLE_LLM_FORECAST = "true"
$env:COUNTRY_COMPARE_LLM_SERVICE_TOKEN = "wrong-token"
# restart backend and verify llm_forecast is unavailable

# Backend enabled and good token
$env:COUNTRY_COMPARE_LLM_SERVICE_TOKEN = "dev-token"
# restart backend and verify llm_forecast is available
```

---

## 13. LLM forecast fallback behavior

Break the provider intentionally:

```powershell
$env:MISTRAL_API_KEY = "invalid-key"
```

Restart the full LLM stack:

```powershell
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

Run an LLM forecast from the UI or API.

Expected:

```text
The backend does not crash.
The UI does not crash.
The result falls back to deterministic baseline behavior where designed.
Diagnostics include clear fallback information.
Provider failure is visible but safe.
No provider secret appears in API response, UI output, exports, or logs.
```

---

## 14. LLM service request limit behavior

Use the UI or API to attempt requests that exceed configured limits, or temporarily lower limits for easier testing.

Examples:

```env
LLM_MAX_HORIZON_YEARS=1
LLM_MAX_HISTORY_POINTS=1
LLM_MAX_INPUT_CHARS=200
LLM_MAX_ADJUSTMENT_PCT=5.0
```

Expected:

```text
Oversized requests fail before a provider call.
The error code is limit_exceeded or an equivalent safe error.
The response includes actionable limit details.
No raw prompt or secret is returned.
The backend/UI handles the failure gracefully.
```

---

## 15. Log and privacy inspection

Inspect logs:

```powershell
docker compose --profile llm logs backend
docker compose --profile llm logs llm-forecast
```

Expected:

```text
No MISTRAL_API_KEY value.
No COUNTRY_COMPARE_LLM_SERVICE_TOKEN value.
No LLM_SERVICE_TOKEN value.
No Authorization header.
No raw provider request body in public deployment mode.
No raw provider response body containing sensitive data.
No stack traces in normal user-facing API responses.
```

Search logs manually for suspicious strings:

```text
MISTRAL_API_KEY
Authorization
Bearer
LLM_SERVICE_TOKEN
COUNTRY_COMPARE_LLM_SERVICE_TOKEN
```

Expected:

```text
No real secret values are present.
```

---

## 16. Export behavior after LLM integration

Run standard workflows:

```text
Single Forecast
Multi-Country Forecast
Predicted Comparison - Single Metric
Predicted Comparison - Profile
Backtest
Normal Comparison
Weighted Scoring
```

Expected:

```text
Existing deterministic workflows still render.
Existing export controls still appear where expected.
CSV/JSON/Markdown exports still work.
LLM diagnostics do not leak secrets into exports.
```

---

## 17. Documentation checks

Open and scan:

```text
README.md
docs/index.md
docs/configuration.md
docs/containerization.md
docs/testing.md
docs/troubleshooting.md
docs/llm_forecast_service.md
docs/manual_qa.md
.env.example
```

Expected:

```text
Docs mention the optional LLM service.
Docs state it is disabled by default.
Docs state it is private and should not be publicly exposed.
Docs explain local profile/override usage.
Docs explain public ZDR gate.
Docs list cost/request limits.
Docs avoid real secrets.
Docs contain current /src-layout commands.
```

---

## 18. CI expectations

Push branch and verify CI.

Expected CI coverage:

```text
Main app tests pass.
Main app ruff/black/mypy pass.
LLM forecast service tests pass.
LLM forecast service ruff/black/mypy pass.
Default Docker build passes.
LLM forecast service Docker image build passes.
No deployment workflow changes are required unless the LLM service is being deployed separately.
```

---

## 19. Cleanup

Stop containers:

```powershell
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml down --volumes --remove-orphans
```

Remove local environment variables:

```powershell
Remove-Item Env:COUNTRY_COMPARE_API_URL -ErrorAction SilentlyContinue
Remove-Item Env:COUNTRY_COMPARE_ENABLE_LLM_FORECAST -ErrorAction SilentlyContinue
Remove-Item Env:COUNTRY_COMPARE_LLM_SERVICE_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:COUNTRY_COMPARE_LLM_SERVICE_URL -ErrorAction SilentlyContinue
Remove-Item Env:MISTRAL_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:MISTRAL_MODEL -ErrorAction SilentlyContinue
Remove-Item Env:LLM_SERVICE_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:LLM_DEPLOYMENT_PROFILE -ErrorAction SilentlyContinue
Remove-Item Env:LLM_REQUIRE_ZDR -ErrorAction SilentlyContinue
Remove-Item Env:MISTRAL_ZDR_CONFIRMED -ErrorAction SilentlyContinue
```

Check git status:

```powershell
git status --short
```

Expected:

```text
Only intentional source/docs/config changes remain.
No .env file is staged.
No generated cache or egg-info files are staged.
No secrets are staged.
```

---

## 20. Final acceptance criteria

The LLM service phase is ready when all of the following are true:

```text
Main app tests pass.
Main app ruff/black/mypy pass.
LLM service tests pass.
LLM service ruff/black/mypy pass.
Default Docker Compose stack works without LLM.
LLM service image builds.
LLM profile starts when requested.
LLM service health/readiness/auth/capabilities behave correctly.
Public ZDR gate blocks readiness when not confirmed.
Backend exposes llm_forecast only when service capabilities succeed.
Backend/UI handle provider failure safely.
Cost/request limits reject oversized requests before provider calls.
No secrets appear in responses, UI, exports, logs, or docs.
Docs and .env examples are updated.
Manual QA checklist is complete.
```
