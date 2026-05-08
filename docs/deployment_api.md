# Backend API deployment notes

The public-beta backend is a read-only FastAPI service. It exposes operational
endpoints at `/health` and `/ready`, and business endpoints under `/api/v1`.

## Runtime model

The backend Docker image is hardened for beta deployment:

- the package is installed with a normal production install, not editable mode;
- the container runs as a non-root `app` user;
- the container honors a platform-injected `PORT` environment variable;
- the healthcheck targets `GET /health` on the configured port;
- API-only deployments should mount `config/` and `data/processed/` read-only.

Example backend-only run:

```bash
docker compose -f compose.api.yml up --build
```

The backend-only compose file mounts:

```yaml
./config:/app/config:ro
./data/processed:/app/data/processed:ro
```

This keeps the API process read-only with respect to deployed configuration and
processed data artifacts.

## Request IDs and structured logging

Every request receives an `X-Request-ID` response header. If the caller sends an
`X-Request-ID` header, the API echoes it. Otherwise, the API generates a request
id for the request.

API access logs are structured JSON and include:

- `request_id`
- `method`
- `path`
- `status_code`
- `duration_ms`

Unhandled exceptions are logged server-side with stack traces. Client-facing
responses remain sanitized and keep the API error envelope shape.

Set the log level with:

```bash
COUNTRY_COMPARE_API_LOG_LEVEL=INFO
```

## Process-local dataset cache

The API assumes processed dataset artifacts are immutable for a deployed process.
The canonical metric dataframe is loaded once per process and reused for later
requests. The service returns defensive copies so request-level code cannot
mutate the cached dataframe.

Cache invalidation is intentionally limited to process restart/redeploy. The API
does not expose dataset refresh, ingestion, or admin cache endpoints.

## Metadata catalog artifact

Offline dataset publishing writes an optional metadata catalog beside the
processed dataset:

```text
data/processed/catalog.json
```

The catalog contains selector-friendly metadata:

- countries
- metrics
- years
- categories
- dataset summary
- dataset identity/version/hash when available

Metadata endpoints use the catalog when it is present and valid. If it is absent
or invalid, the API falls back to deriving metadata from the processed dataframe.

To regenerate the catalog from an existing processed dataset:

```bash
python scripts/generate_metadata_catalog.py --dataset-path data/processed/metrics.parquet
```

## Backend dependency footprint

The backend Docker image installs the package with the API optional dependency
group:

```bash
python -m pip install ".[api]"
```

## Dataset replacement and rollback

The API does not expose dataset refresh or replacement endpoints. Processed
dataset artifacts are replaced offline and activated by backend restart or
redeploy.

A complete dataset artifact set is:

```text
data/processed/metrics.parquet
data/processed/metrics_manifest.json
data/processed/catalog.json

## CI and security scans

GitHub Actions run:

- pytest
- ruff
- black `--check`
- mypy
- static import/layout guards
- package build
- install from built wheel and sdist
- Docker Compose build
- backend container smoke checks for `/health`, `/ready`, and metadata
- `pip-audit` in non-blocking mode
- Trivy backend image scan in non-blocking mode

The dependency and container scans are intentionally non-blocking during public
beta. To tighten later, remove `|| true` from the `pip-audit` step and set the
Trivy action `exit-code` to `1`.

## Operational troubleshooting

`/health` should stay lightweight and should not require dataset/config loading.
Use it for process liveness.

`/ready` is strict. It validates dataset existence, schema/manifest validity,
and dataset-aware configuration validity. A failed `/ready` normally means one
of these artifacts is missing or inconsistent:

- `data/processed/metrics.parquet`
- `data/processed/metrics_manifest.json`
- `config/metrics.yaml`
- `config/scoring_profiles.yaml`

For request-specific issues, capture the `X-Request-ID` response header and look
for the same `request_id` in backend logs.