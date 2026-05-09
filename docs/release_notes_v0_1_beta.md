# Country Compare v0.1 Beta Release Notes

## Status

`v0.1 beta` is the first beta checkpoint for the full local, API, and containerized Country Compare application.

This release is intended for controlled public beta usage with a read-only backend API, Streamlit UI, Docker Compose deployment support, and offline-managed dataset artifacts.

## Included

### Comparison workflows

- Single-metric country comparison.
- Multi-metric country comparison.
- Weighted/profile scoring workflows.
- Result summaries, detailed tables, and exports where available.
- HTTP/API-safe result serialization for UI and API clients.

### Prediction workflows

- Single forecast.
- Multi-country forecast.
- Predicted comparison.
- Backtest.
- Prediction quality and limitations panels.
- Forecast and backtest visualizations where returned data supports them.
- Forecast exports where supported.
- Baseline statistical prediction methods only.

### Backend API

- Read-only FastAPI backend.
- Operational endpoints:
  - `GET /health`
  - `GET /ready`
- Metadata endpoints.
- Comparison endpoints.
- Scoring endpoint.
- Prediction endpoints.
- JSON-safe response envelopes and table payloads.
- Consistent API error envelopes.
- Sanitized client-facing unexpected errors.
- Server-side exception logging with stack traces.
- Request ID support:
  - accepts inbound `X-Request-ID`
  - generates a request ID when missing
  - returns `X-Request-ID` on responses
  - includes request IDs in structured logs
- Optional API-key protection through environment configuration.

### Dataset and metadata handling

- Processed metric dataset loaded from `data/processed/metrics.parquet`.
- Dataset manifest support through `data/processed/metrics_manifest.json`.
- Precomputed metadata catalog support through `data/processed/catalog.json`.
- Metadata endpoints use the catalog when available and fall back to dataframe-derived metadata when needed.
- Process-local dataframe cache for the API process.
- Offline dataset replacement model with backend restart/redeploy required after artifact replacement.

### Streamlit UI

- Local in-process mode.
- HTTP-backed mode.
- Docker/container mode.
- Streamlit-native charts reconstructed from returned tables in HTTP/container mode.
- Duplicate primary table display guard.
- Export controls preserved where supported.
- Prediction result panels, charts, diagnostics, quality panels, and export controls.
- Config inspection and local UI workflows remain available where supported.

### Container support

- Docker Compose split between backend and UI containers.
- Backend available on port `8000` by default.
- UI available on port `8501` by default.
- Backend-only Compose deployment through `compose.api.yml`.
- Backend image hardening:
  - production package install
  - non-root container user
  - `PORT`-compatible startup
  - runtime healthcheck
  - API-only dependency footprint
- Recommended read-only mounts for backend config and processed data.
- Runtime path configuration for container deployments:
  - `COUNTRY_COMPARE_METRICS_CONFIG=/app/config/metrics.yaml`
  - `COUNTRY_COMPARE_SCORING_CONFIG=/app/config/scoring_profiles.yaml`
  - `COUNTRY_COMPARE_STORE_PATH=/app/data/processed/metrics.parquet`

### Packaging

- `/src` package layout.
- Package imports remain `country_compare`.
- Backend installs with the `api` optional dependency group.
- UI installs with the `ui` optional dependency group.
- Development installs use the `dev` optional dependency group.
- Wheel and sdist package build checks are included in CI.

### CI and validation

- Python tests.
- Formatting checks with Black.
- Linting with Ruff.
- Type checks with mypy.
- Static `/src` layout guard.
- Package build checks.
- Wheel install checks for API and UI extras.
- Sdist install check.
- Docker Compose build.
- Default Compose backend smoke checks.
- Backend-only Compose smoke checks.
- Smoke checks for:
  - `/health`
  - `/ready`
  - metadata endpoints
  - comparison endpoint
  - request ID passthrough
- Non-blocking dependency scan with `pip-audit`.
- Non-blocking container scan with Trivy.

### Documentation

- API documentation.
- Containerization documentation.
- Backend API deployment notes.
- Dataset artifact replacement and rollback workflow.
- `.env.example` for local/container runtime configuration.

## Explicitly not included

`v0.1 beta` does not include:

- write API endpoints
- config editing API endpoints
- scoring profile editing API endpoints
- dataset refresh API endpoints
- ingestion execution API endpoints
- scheduled ingestion or processing
- online dataset replacement or cache invalidation endpoints
- user accounts
- OAuth login
- role-based access control
- multi-tenant authorization
- Kubernetes manifests
- cloud-provider-specific deployment files
- new prediction algorithms beyond the current baseline methods

## Known limitations

- Forecasts are baseline statistical projections, not guarantees.
- Sparse, stale, or noisy historical data can reduce prediction reliability.
- Backtest performance does not guarantee future forecast performance.
- HTTP/container mode visualizations depend on returned table shapes.
- Some result tables may not be chartable; in that case, the UI should preserve table output and show explanatory text.
- The API is intentionally read-only for this beta.
- Dataset replacement is an offline operator workflow.
- Dataset cache invalidation requires backend restart or redeploy.
- Dependency and container security scans are currently non-blocking in CI.
- Optional API-key protection is available, but full user authentication and authorization are not included.

## Dataset artifact model

A complete dataset release consists of:

```text
data/processed/metrics.parquet
data/processed/metrics_manifest.json
data/processed/catalog.json
```

These files should be generated, validated, promoted, backed up, and rolled back together.

After replacing dataset files in a deployed environment, restart or redeploy the backend process so the process-local dataframe cache loads the new dataset.

See `docs/dataset_replacement.md` for the full publish, validate, replace, verify, and rollback workflow.

## Validation checklist

Before tagging or publishing this beta, run:

```bash
python scripts/check_static_guards.py
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
python -m build
```

Run package install checks, or verify that CI passes the package-build job.

Generate or verify processed dataset artifacts:

```bash
python scripts/update_parquet_data_wb.py --skip-audit
test -f data/processed/metrics.parquet
test -f data/processed/metrics_manifest.json
test -f data/processed/catalog.json
```

Build and run Docker Compose:

```bash
docker compose down --volumes --remove-orphans
docker compose up --build
```

Verify:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8000/api/v1/metadata/dataset
http://localhost:8501
```

Run the API smoke script against the default Compose backend:

```bash
python scripts/smoke_api_container.py --base-url http://127.0.0.1:8000
```

Verify backend-only API mode:

```bash
docker compose -f compose.api.yml down --volumes --remove-orphans
docker compose -f compose.api.yml up --build
python scripts/smoke_api_container.py --base-url http://127.0.0.1:8000
```

Verify local UI mode:

```bash
unset COUNTRY_COMPARE_API_URL
country-compare ui
```

Verify HTTP-backed UI mode:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

Manually verify these UI workflows:

```text
Overview page loads dataset and config status
Compare: single-metric comparison
Compare: multi-metric comparison
Compare: weighted/profile scoring
Prediction: single forecast
Prediction: multi-country forecast
Prediction: predicted comparison
Prediction: backtest
Exports render without Streamlit duplicate-key errors
Debug mode shows useful details without breaking normal flows
```

## Deployment notes

For backend API deployments, configure:

```bash
COUNTRY_COMPARE_STORE_BACKEND=parquet
COUNTRY_COMPARE_STORE_PATH=/app/data/processed/metrics.parquet
COUNTRY_COMPARE_METRICS_CONFIG=/app/config/metrics.yaml
COUNTRY_COMPARE_SCORING_CONFIG=/app/config/scoring_profiles.yaml
COUNTRY_COMPARE_API_ENABLE_DOCS=false
COUNTRY_COMPARE_API_LOG_LEVEL=INFO
```

Optional API-key protection can be enabled with:

```bash
COUNTRY_COMPARE_API_KEY=<secret>
```

When API-key protection is enabled, clients must send the configured key according to the API client/security documentation.

For public beta deployments, mount backend config and processed data read-only where possible:

```text
/app/config:ro
/app/data/processed:ro
```

## Upgrade notes

The project uses `/src` layout. Direct filesystem Streamlit execution should use:

```bash
python -m streamlit run src/country_compare/ui/app.py
```

Module paths remain unchanged:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Docker Compose users should rebuild images after upgrading:

```bash
docker compose down --volumes --remove-orphans
docker compose build --no-cache
docker compose up
```

If containerized paths appear to resolve under `site-packages`, verify that the runtime path environment variables point to `/app/config` and `/app/data/processed`.

## Recommended beta operating model

- Deploy first to staging or private beta.
- Verify `/health`, `/ready`, metadata, comparison, prediction, and UI workflows.
- Keep dataset artifacts immutable during a running deployment.
- Replace datasets offline using the documented artifact replacement workflow.
- Restart or redeploy after dataset replacement.
- Capture `X-Request-ID` values when reporting API issues.
- Monitor structured backend logs, 4xx/5xx rates, memory usage, and readiness failures.
