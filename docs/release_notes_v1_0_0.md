# Release notes: Country Compare v1.0.0

Release date: 2026-06-01  
Release type: First major release  
Recommended tag: `v1.0.0`

## Summary

Country Compare `v1.0.0` is the first major release of the project. It promotes the current implementation from the beta baseline into a stable, documented application for comparing countries across economic, health, governance, and social metrics.

This release delivers a complete end-to-end workflow: public-data-style inputs are converted into a canonical long-format metrics dataset, then used for country comparison, weighted scoring, baseline forecasting, predicted comparisons, backtesting, diagnostics, exports, a Streamlit UI, a read-only FastAPI backend, Docker Compose deployment, and an optional private LLM forecast microservice.

The main architectural commitment in this release is the separation between domain logic, services, clients, API transport, and UI presentation. The FastAPI backend remains a read-only transport adapter over the service/domain core, while the Streamlit UI can run either locally in-process or against the backend over HTTP.

## Release highlights

### Stable application architecture

- Adopted the `src/country_compare` package layout.
- Kept framework-neutral domain logic under `comparison`, `prediction`, `data`, `config`, `scoring`, `metrics`, and `pipelines`.
- Centralized app-facing orchestration in the `services` and facade layer.
- Added a client abstraction so the UI can use either local in-process services or an HTTP backend without duplicating workflow logic.
- Kept Streamlit-specific behavior inside the UI layer.
- Kept FastAPI route handlers focused on request parsing, API limits, service calls, serialization, and error mapping.

### Canonical country metrics dataset

- Standardized on a long-format dataset contract with one row per `country_code + metric_id + year`.
- Preserved required metric metadata such as country name, metric name, unit, source, category, and `higher_is_better`.
- Added dataset metadata support for row counts, country counts, metric counts, year bounds, dataset versions, checksums, schema status, and category summaries.
- Added validation flows for data and configuration readiness.
- Added manifest-oriented pipeline support for source acquisition, processing, auditing, and publishing.

### Country comparison and weighted scoring

- Added single-metric country comparison.
- Added multi-metric comparison.
- Added weighted profile scoring based on configured scoring profiles.
- Preserved `higher_is_better` semantics for ranking and score interpretation.
- Added structured diagnostics, warnings, tables, chart-ready payloads, and export-friendly result objects.

### Prediction, backtesting, and predicted comparison

- Added baseline single-metric forecasting for one or more countries.
- Added deterministic forecast methods such as `linear_trend` and `last_observed` style behavior.
- Added fallback behavior for sparse or unsuitable histories.
- Added holdout backtesting for country/metric series.
- Added predicted single-metric comparison.
- Added predicted profile comparison.
- Added predicted multi-metric comparison.
- Added prediction quality and diagnostics payloads suitable for UI rendering and API clients.

Forecasts in this release should be treated as baseline statistical projections, not guarantees. Sparse histories, stale data, methodology changes, and external shocks can make forecasts unreliable.

### Streamlit UI

- Added an interactive Streamlit UI for selecting countries, metrics, scoring profiles, and forecast options.
- Added local mode for in-process service calls when `COUNTRY_COMPARE_API_URL` is unset.
- Added HTTP-backed mode when `COUNTRY_COMPARE_API_URL` is configured.
- Added result panels for comparisons, scoring, predictions, diagnostics, warnings, and limitations.
- Added export controls for tables, diagnostics, and Markdown summaries.
- Used JSON-safe and chart-ready payloads for HTTP-backed UI rendering.

### Read-only FastAPI backend

The backend API is included as a stable read-only adapter for UI/backend separation and service integration.

Operational endpoints:

```text
GET /health
GET /ready
GET /ready/llm
GET /metrics
```

Metadata endpoints:

```text
GET /api/v1/metadata/dataset
GET /api/v1/metadata/countries
GET /api/v1/metadata/metrics
GET /api/v1/metadata/years
GET /api/v1/metadata/profiles
GET /api/v1/metadata/prediction-methods
```

Comparison and scoring endpoints:

```text
POST /api/v1/compare/single-metric
POST /api/v1/compare/multi-metric
POST /api/v1/score/profile
```

Prediction endpoints:

```text
POST /api/v1/prediction/single-metric
POST /api/v1/prediction/backtest
POST /api/v1/prediction/compare/single-metric
POST /api/v1/prediction/compare/profile
POST /api/v1/prediction/compare/multi-metric
```

All computation endpoints return JSON-safe result envelopes with fields such as `ok`, `mode`, `request`, `summary`, `metadata`, `diagnostics`, `warnings`, `messages`, `tables`, `charts`, and `error`.

API serialization converts pandas, numpy, and datetime values into JSON-safe scalars or `null`. Large table payloads can be limited by the API max-records setting.

### API operations, security, and observability

- Added process liveness through `/health`.
- Added strict traffic readiness through `/ready`.
- Added backend-to-LLM readiness through `/ready/llm`.
- Added Prometheus-compatible metrics through `/metrics`.
- Added request ID support through `X-Request-ID`.
- Added structured JSON access logging with request context.
- Added optional API-key protection through `COUNTRY_COMPARE_API_KEY`.
- Added CORS configuration for trusted UI origins.
- Added request limit settings for countries, metrics, forecast horizons, holdout windows, records, and `top_n` values.
- Added sanitized client-facing error responses while preserving server-side exception logging.

### Docker and Compose deployment

- Added separate backend and UI container builds.
- Added default Docker Compose stack for the backend and UI.
- Added HTTP-backed UI behavior in Compose through `COUNTRY_COMPARE_API_URL=http://backend:8000`.
- Added optional LLM service profile for local private LLM forecast testing.
- Added container smoke validation support.

### Optional private LLM forecast service

This release includes an optional `llm_forecast` capability as an experimental bounded adjustment on top of deterministic baseline forecasts.

The LLM forecast service:

- lives under `services/llm_forecast_service/`,
- is disabled by default,
- should not be exposed publicly,
- is token-protected,
- is gated by backend configuration,
- reports capabilities before the backend advertises `llm_forecast`,
- requires structured-output and bounded-adjustment support,
- should never be treated as an authoritative forecast source.

The backend advertises `llm_forecast` only when the feature flag is enabled, service URL and token are configured, the private service is reachable, `/v1/capabilities` succeeds, and the service reports the required capabilities.

### CLI and operational commands

Primary CLI commands included in this release:

```bash
country-compare ui
country-compare validate-config
country-compare validate-data
country-compare update-data --manifest config/source_manifests/world_bank_real_data.yaml
```

Common local runtime commands:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
python -m streamlit run src/country_compare/ui/app.py
```

Common Docker commands:

```bash
docker compose up --build
docker compose build
docker compose --profile llm build llm-forecast
docker compose down
```

### Testing and validation coverage

The release is covered by unit, integration, smoke, API, client, UI, service, LLM service, and data-correctness tests.

Recommended validation before tagging:

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

Also complete manual QA for:

- local Streamlit UI,
- HTTP-backed Streamlit UI,
- backend readiness and metadata endpoints,
- comparison and scoring workflows,
- prediction and backtesting workflows,
- export behavior,
- Docker Compose startup,
- optional LLM forecast gating and readiness.

## Breaking changes

This is the first major release, so there is no previous stable major-version API contract to preserve.

Users upgrading from the beta baseline should treat this release as the stabilization point. From `v1.0.0` onward, changes to documented public behavior should be handled through normal semantic-versioning expectations.

## Migration notes from beta

When promoting the beta baseline to `v1.0.0`:

1. Update package/version metadata from `0.1.0` to `1.0.0` where applicable.
2. Replace beta references in documentation with `v1.0.0` or first major release language.
3. Rebuild the backend and UI containers.
4. Re-run validation commands and the full test suite.
5. Verify the Streamlit UI in both local mode and HTTP-backed mode.
6. Verify `/health`, `/ready`, `/ready/llm`, and `/metrics` in the backend runtime.
7. Tag the release with `v1.0.0` after validation passes.

## Known limitations

- The backend API is intentionally read-only.
- The API does not expose ingestion, data refresh, config editing, scoring-profile editing, or pipeline execution endpoints.
- Authentication is limited to optional API-key protection; full user authentication and authorization are not part of this release.
- Forecasts are baseline projections and should not be interpreted as guarantees.
- `llm_forecast` is experimental, private, gated, and disabled by default.
- Server-side persistent export generation is not part of the read-only API.
- Data quality depends on the processed dataset, source manifests, and validation rules used to build the release dataset.

## Recommended release assets

For a complete `v1.0.0` release, attach or publish:

- Git tag: `v1.0.0`
- Source archive generated by GitHub release tooling
- Backend Docker image tagged with `1.0.0`
- UI Docker image tagged with `1.0.0`
- Optional LLM forecast service image tagged with `1.0.0`, if publishing it internally
- Updated documentation under `/docs`
- Updated root `README.md`
- Updated `services/llm_forecast_service/README.md`

## Suggested GitHub release description

Country Compare `v1.0.0` is the first major release of the project. It includes the stable canonical data contract, Streamlit UI, read-only FastAPI backend, comparison and weighted scoring workflows, baseline forecasting, predicted comparisons, backtesting, diagnostics, exports, Docker Compose deployment, and an optional private LLM forecast microservice.

This release establishes the stable architecture for future development: domain and service logic remain framework-neutral, the backend API stays read-only, the UI talks through a local/HTTP client abstraction, and API responses are JSON-safe for containerized operation.

Before tagging, confirm that package metadata is updated to `1.0.0`, all validation and test commands pass, and both local and HTTP-backed UI flows complete successfully.
