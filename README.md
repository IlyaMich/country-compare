# Country Compare

Country Compare is a Python 3.11 application for comparing countries across economic, health, governance, and social metrics. It converts public-data-style inputs into a canonical long-format dataset, then exposes comparison, weighted scoring, baseline forecasting, predicted comparison, backtesting, diagnostics, exports, a Streamlit UI, a read-only FastAPI backend, and an optional private LLM forecast microservice.

The current implementation is designed around a stable service/domain core with two UI access modes:

```text
Local mode:      Streamlit UI -> in-process client -> services/facade -> domain/data/config
Container mode:  Streamlit UI -> HTTP client -> FastAPI backend -> services/facade -> domain/data/config
Optional LLM:    FastAPI backend -> private token-protected llm-forecast service -> provider API
```

The repository currently keeps the backend API read-only. It does not expose ingestion, config editing, scoring-profile editing, data refresh, or server-side export write endpoints.

## Main features

- Streamlit UI for selecting countries, metrics, scoring profiles, and forecast options.
- Single-metric and multi-metric comparisons.
- Weighted profile scoring.
- Baseline prediction workflows with `linear_trend` and `last_observed` style methods.
- Prediction backtesting and predicted comparisons.
- Optional `llm_forecast` method that performs bounded adjustments on deterministic forecasts through a private service.
- Export-first result handling for tables, diagnostics, and Markdown summaries.
- FastAPI backend with JSON-safe response envelopes, request IDs, readiness checks, optional API-key protection, CORS settings, and Prometheus-compatible metrics endpoint.
- Docker Compose support for backend, UI, and optional LLM service profile.
- Data/config validation and integration/data-correctness test coverage.

## Repository layout

```text
src/country_compare/
  api/          FastAPI app, schemas, routes, errors, security, serialization
  clients/      local and HTTP client abstraction used by the UI
  cli/          command-line entry points
  comparison/   comparison workflows
  config/       config models, loaders, validators
  data/         canonical data contract, validation, stores, ingestion helpers
  exports/      CSV / JSON / Markdown export helpers
  metrics/      filtering and normalization helpers
  output/       chart and output helpers
  pipelines/    acquisition, processing, audit, publish flows
  prediction/   forecasting, backtesting, predicted comparison, visualization data
  scoring/      weighted scoring workflows
  services/     app-facing orchestration and result models
  settings/     centralized application settings
  ui/           Streamlit views, components, state

services/llm_forecast_service/
  src/llm_forecast_service/  private LLM adjustment service
  tests/                     service tests
  Dockerfile
  Makefile
  pyproject.toml
  README.md

config/       metric metadata, scoring profiles, source manifests, demo config
data/         processed/example data and local exports
docs/         project documentation
scripts/      demo, data, manifest, smoke, and guard scripts
tests/        unit, integration, smoke, API, client, UI, and data correctness tests
```

Use package imports such as `import country_compare`; do not import from `src.country_compare`.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the Streamlit app locally with in-process services:

```bash
country-compare ui
```

or:

```bash
python -m streamlit run src/country_compare/ui/app.py
```

Run the FastAPI backend locally:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Useful backend URLs:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8000/ready/llm
http://localhost:8000/docs
```

Run the UI against the HTTP backend:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

Windows PowerShell:

```powershell
$env:COUNTRY_COMPARE_API_URL = "http://localhost:8000"
python -m streamlit run src/country_compare/ui/app.py
```

## Docker Compose

Start the normal backend + UI stack:

```bash
docker compose up --build
```

Default local URLs:

```text
Backend: http://localhost:8000
UI:      http://localhost:8501
```

In Compose mode the UI calls the backend through:

```text
COUNTRY_COMPARE_API_URL=http://backend:8000
```

Stop the stack:

```bash
docker compose down
```

Build containers without starting them:

```bash
docker compose build
docker compose --profile llm build llm-forecast
```

## API overview

Operational endpoints are unversioned:

```text
GET /health
GET /ready
GET /ready/llm
GET /metrics
```

Business endpoints use `/api/v1`:

```text
GET  /api/v1/metadata/dataset
GET  /api/v1/metadata/countries
GET  /api/v1/metadata/metrics
GET  /api/v1/metadata/years
GET  /api/v1/metadata/profiles
GET  /api/v1/metadata/prediction-methods
POST /api/v1/compare/single-metric
POST /api/v1/compare/multi-metric
POST /api/v1/score/profile
POST /api/v1/prediction/single-metric
POST /api/v1/prediction/backtest
POST /api/v1/prediction/compare/single-metric
POST /api/v1/prediction/compare/profile
POST /api/v1/prediction/compare/multi-metric
```

All computation endpoints return a JSON-safe result envelope with `ok`, `mode`, `request`, `summary`, `metadata`, `diagnostics`, `warnings`, `messages`, `tables`, `charts`, and `error` fields. Pandas, numpy, and datetime values are serialized into JSON-safe scalars or `null`.

Set `COUNTRY_COMPARE_API_KEY` on the backend to protect non-operational endpoints. Set the same value in the UI process when `COUNTRY_COMPARE_API_URL` is enabled.

## Common commands

```bash
country-compare ui
country-compare validate-config
country-compare validate-data
country-compare update-data --manifest config/source_manifests/world_bank_real_data.yaml
```

## Tests and checks

Main application:

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
```

LLM service:

```bash
cd services/llm_forecast_service
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
cd ../..
```

Makefile shortcuts, when available:

```bash
make check
make llm-check
make check-all
make container-build
```

## Optional LLM forecast service

The `llm_forecast` method is experimental and disabled by default. It should be used only as a bounded adjustment to deterministic baseline forecasts and should not be treated as authoritative.

Start the local LLM profile with local overrides:

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

Typical local configuration:

```text
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=dev-token
MISTRAL_API_KEY=<local-secret>
MISTRAL_MODEL=mistral-large-latest
```

The backend only advertises `llm_forecast` when the feature flag is enabled, the service URL/token are configured, the private service is reachable, `/v1/capabilities` succeeds, and the service reports structured-output plus bounded-adjustment support.

## Documentation

Start with `docs/index.md`. Key docs:

- `docs/getting_started.md` for local and Compose quick start.
- `docs/api.md` for endpoint contracts and examples.
- `docs/architecture.md` for layer boundaries.
- `docs/configuration.md` for config and environment variables.
- `docs/data_contract.md` for canonical dataset requirements.
- `docs/prediction.md` and `docs/prediction_methods.md` for forecasting workflows.
- `docs/llm_forecast_service.md` for the optional private LLM service.
- `docs/testing.md` and `docs/manual_qa.md` for validation.
- `docs/deployment_api.md` for deploying the backend.
