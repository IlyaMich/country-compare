# Backend API deployment notes

The public-beta backend is a read-only FastAPI service. It exposes operational
endpoints at `/health` and `/ready`, and business endpoints under `/api/v1`.

## Runtime model

The backend Docker image is hardened for beta deployment:

- the package is installed with a normal production install, not editable mode;
- the container runs as a non-root `app` user;
- the container honors a platform-injected `PORT` environment variable;
- the healthcheck targets `GET /health` on the configured port;
- API-only deployments may either use an image with embedded processed data or
  mount `config/` and `data/processed/` read-only.

API-only deployments can run in either of these beta-safe modes:

1. **Embedded dataset image**: generate `data/processed/*` in CI before building
   `Dockerfile.backend`, then deploy that exact image.
2. **Read-only mounted dataset**: deploy the backend image and mount `config/` and
   `data/processed/` read-only from the hosting platform.

The embedded dataset image is the recommended first public-beta path because the
image is immutable, smoke-testable, and easy to roll back.

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
```

## Release image pipeline

The CI workflow builds and validates a deployable backend API image. The release
image pipeline intentionally generates the processed dataset before the backend
image is built so the image can contain a complete immutable dataset release.

On every CI run, the Docker job:

1. generates `data/processed/*` using `scripts/update_parquet_data_wb.py`;
2. verifies `metrics.parquet`, `metrics_manifest.json`, and `catalog.json`;
3. builds the normal Compose services;
4. smoke-tests the default Compose backend;
5. smoke-tests the backend-only Compose service;
6. builds `Dockerfile.backend` as `country-compare-backend:ci`;
7. smoke-tests that image without host data volumes and with an API key enabled;
8. runs the non-blocking Trivy container scan.

For pushes to `main` and tags matching `v*`, CI publishes the exact smoke-tested
backend image to GitHub Container Registry:

```text
ghcr.io/<owner>/country-compare-api:sha-<short-sha>
ghcr.io/<owner>/country-compare-api:main
ghcr.io/<owner>/country-compare-api:latest
ghcr.io/<owner>/country-compare-api:<git-tag>
```

`main` and `latest` are only published from the `main` branch. Version tags are
published from matching Git tags. Pull requests and feature branches build and
smoke-test images but do not publish them.

## Deployment workflow

`.github/workflows/deploy-api.yaml` is a provider-neutral manual deployment
workflow. It expects the hosting provider to deploy a previously published GHCR
image instead of rebuilding the repository itself.

Configure these GitHub environment secrets for the target environment, for
example `beta`:

```text
COUNTRY_COMPARE_API_DEPLOY_WEBHOOK_URL   required
COUNTRY_COMPARE_API_DEPLOY_WEBHOOK_TOKEN optional
COUNTRY_COMPARE_API_BASE_URL             required for post-deploy smoke tests
COUNTRY_COMPARE_API_KEY                  optional, required if the public API is key-protected
```

The deployment workflow sends this JSON payload to the webhook:

```json
{
  "image": "ghcr.io/<owner>/country-compare-api:<tag>",
  "environment": "beta",
  "service": "country-compare-api"
}
```

For providers whose deploy hooks ignore request bodies, configure the provider
service to consume a stable published tag such as `main` or `latest`. For
providers with APIs that accept image names, wire the webhook receiver to deploy
the `image` value from the payload.

After triggering the provider deployment, the workflow can run the same smoke
script against the public API URL:

```bash
python scripts/smoke_api_container.py \
  --base-url "$COUNTRY_COMPARE_API_BASE_URL" \
  --api-key "$COUNTRY_COMPARE_API_KEY"
```

Use `/health` for hosting-platform liveness checks. Use `/ready` in release and
post-deploy smoke checks with the API key when key protection is enabled.

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
- backend container smoke checks for `/health`, `/ready`, metadata, and comparison
- backend release image smoke checks without host data volumes
- GHCR image publishing for `main` and `v*` tag pushes
- provider-neutral manual deployment workflow
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