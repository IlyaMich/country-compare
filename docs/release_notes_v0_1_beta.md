# Release notes: current beta baseline

This file is retained for release-history compatibility. The current implementation is ready to serve as the documented baseline for a first major release once package/version metadata and tags are updated by the release process.

## Included capabilities

- Canonical long-format country metrics dataset.
- Config validation and data validation commands.
- Streamlit UI with local and HTTP-backed client modes.
- Read-only FastAPI backend.
- Metadata, comparison, scoring, prediction, backtesting, and predicted-comparison endpoints.
- JSON-safe result envelopes with warnings, diagnostics, tables, and chart-ready payloads.
- Request ID propagation and structured API access logging.
- Optional API-key protection.
- Readiness checks for backend and backend-to-LLM service integration.
- Prometheus-compatible metrics endpoint.
- Docker Compose runtime for backend and UI.
- Optional private LLM forecast service profile.
- Unit, integration, smoke, client, UI, API, LLM service, and data correctness tests.

## Current endpoint surface

Operational:

```text
GET /health
GET /ready
GET /ready/llm
GET /metrics
```

Business:

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

## Boundaries retained

- Backend API remains read-only.
- UI calls through the client abstraction.
- Domain modules remain framework-neutral.
- LLM forecast service remains optional, private, token-protected, bounded, and experimental.
- Data refresh and ingestion remain out-of-band pipeline operations, not API endpoints.

## Validation before tagging a major release

```bash
country-compare validate-config
country-compare validate-data
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

Also complete `manual_qa.md` for local UI, HTTP UI, backend API, predictions, exports, and optional LLM behavior.
