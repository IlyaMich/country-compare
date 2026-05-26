# Testing Guide

Country Compare uses unit, integration, smoke, service, container, and manual QA checks.

Run commands from the repository root unless a section says otherwise.

---

## Full main-app test and quality suite

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
docker compose build
```

---

## LLM forecast service test and quality suite

The LLM forecast service is an independently installable package.

Run from the service directory:

```bash
cd services/llm_forecast_service
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
cd ../..
```

Or use the Makefile from the repository root:

```bash
make llm-install-dev
make llm-check
```

---

## Recommended full local verification before pushing

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare

cd services/llm_forecast_service
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
cd ../..

docker compose build
docker compose --profile llm build llm-forecast
```

If using Make:

```bash
make check
make llm-check
make check-all
make container-build
```

---

## Focused test commands

### UI helper tests

```bash
python -m pytest tests/unit/ui
```

Use these for:

- dataframe shaping
- result panel summaries
- prediction quality helpers
- chart-data helpers
- Streamlit-independent logic

### Client tests

```bash
python -m pytest tests/unit/clients
```

Use these when changing:

- local client behavior
- HTTP client behavior
- HTTP result reconstruction
- API envelope handling
- export adapter behavior

### API tests

```bash
python -m pytest tests/integration/api
```

Use these when changing:

- FastAPI routes
- request schemas
- response schemas
- serialization
- error mapping
- readiness behavior

### Prediction tests

```bash
python -m pytest tests/unit/prediction
```

Use these when changing:

- forecasting methods
- fallback behavior
- LLM forecast backend integration
- diagnostics
- backtesting
- prediction comparison bridges

### LLM forecast service tests

```bash
cd services/llm_forecast_service
python -m pytest
```

Use these when changing:

- LLM service settings
- auth behavior
- request limits
- provider adapters
- Mistral integration
- privacy/redaction behavior
- public deployment ZDR gate
- service readiness/capabilities

---

## What to test

### UI changes

Prefer tests for pure helpers that do not require launching Streamlit.

Examples:

- comparison chart dataframe shaping
- predicted comparison summary extraction
- backtest actual-vs-predicted chart shaping
- quality/limitations text behavior
- empty dataframe handling
- missing column handling
- result table selection logic

### HTTP client changes

Test that JSON-safe API envelopes reconstruct into the expected local-style result objects.

Important cases:

- main table present
- extra tables present
- warnings/messages preserved
- diagnostics preserved
- export adapter behavior preserved
- no duplicate main table behavior

### API changes

Test:

- route status codes
- request DTO validation
- error response shape
- JSON-safe serialization
- no raw pandas objects
- readiness behavior
- API key behavior, when configured

### Prediction changes

Test:

- sparse data behavior
- fallback diagnostics
- failed series handling
- backtest error metrics
- chart-ready table construction
- warning propagation
- predicted comparison ranking behavior

### LLM backend integration changes

Test:

- `llm_forecast` unavailable when disabled
- unavailable when service URL/token is missing
- unavailable when `/v1/capabilities` fails
- available when capability check succeeds
- remote forecast payload mapping
- remote HTTP errors are safe
- no secret leaks in exception messages
- deterministic fallback behavior on remote failure

### LLM service changes

Test:

- `/health` stays lightweight
- `/ready` validates provider config
- `/ready` enforces public ZDR gate
- `/v1/capabilities` requires bearer auth
- `/v1/capabilities` returns 503 when not ready
- forecast route requires bearer auth
- forecast route enforces max horizon/history/input limits
- provider output is schema-validated
- provider output is bounded against baseline
- Mistral errors map to safe service errors
- metadata is redacted/allow-listed

### Comparison/scoring changes

Test:

- single-metric comparison
- multi-metric comparison
- profile scoring
- rank/score behavior
- missing data behavior
- chart helper behavior

---

## Docker validation

Default stack:

```bash
docker compose build
docker compose up --build
```

Manual URLs:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8501
```

LLM service image build:

```bash
docker compose --profile llm build llm-forecast
```

LLM local stack with host-side service port:

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

Manual URLs:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8080/health
http://localhost:8080/ready
http://localhost:8501
```

Capabilities check:

```bash
curl -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

PowerShell:

```powershell
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8080/v1/capabilities
```

---

## Manual QA

Use:

```text
docs/manual_qa.md
docs/llm_forecast_service.md
```

before tagging or publishing the beta.

At minimum, manually verify:

- local Streamlit mode
- HTTP-backed Streamlit mode
- default Docker Compose mode
- backend `/health`
- backend `/ready`
- comparison workflows
- prediction workflows
- export controls
- LLM service disabled-by-default behavior
- LLM profile startup
- LLM service readiness
- LLM service auth
- public ZDR gate
- secret redaction in logs and responses