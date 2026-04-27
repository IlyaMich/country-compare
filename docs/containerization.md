# Containerization

Country Compare can run as two separate containers:

1. a FastAPI backend container
2. a Streamlit UI container

The containerized setup is intended for local integration testing and development of the UI/backend split. It is not yet a production deployment template.

## Runtime architecture

```text
Browser
  ↓
Streamlit UI container
  ↓ HTTP
FastAPI backend container
  ↓
country_compare.services
  ↓
existing domain modules
  ↓
processed canonical dataset
```

The backend exposes the read-only API.

The UI calls the backend over HTTP when `COUNTRY_COMPARE_API_URL` is set.

## Files

The container setup uses:

```text
Dockerfile.backend
Dockerfile.ui
docker-compose.yml
.dockerignore
```

Supporting docs:

```text
README.md
docs/api.md
docs/containerization.md
```

## Services

### Backend service

The backend container runs:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Published host port:

```text
8000
```

Useful URLs:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8000/docs
```

### UI service

The UI container runs:

```bash
python -m streamlit run country_compare/ui/app.py --server.address=0.0.0.0 --server.port=8501
```

Published host port:

```text
8501
```

Useful URL:

```text
http://localhost:8501
```

Inside Docker Compose, the UI calls the backend through the internal Compose service name:

```text
http://backend:8000
```

## Environment variables

### Backend

Common backend environment variables:

```text
COUNTRY_COMPARE_API_ENABLE_DOCS=true
COUNTRY_COMPARE_STORE_BACKEND=parquet
```

API-specific variables:

```text
COUNTRY_COMPARE_API_CORS_ORIGINS
COUNTRY_COMPARE_API_MAX_RECORDS
COUNTRY_COMPARE_API_ENABLE_DOCS
```

### UI

The important UI variable in containerized mode is:

```text
COUNTRY_COMPARE_API_URL=http://backend:8000
```

Client selection behavior:

```text
COUNTRY_COMPARE_API_URL unset -> Streamlit uses local in-process services
COUNTRY_COMPARE_API_URL set   -> Streamlit uses the FastAPI backend over HTTP
```

In Docker Compose mode, this should be set for the UI container.

## Mounted paths

The Compose setup mounts project config and data into both containers:

```text
./config -> /app/config
./data   -> /app/data
```

Recommended mount behavior:

```text
config: read-only
data: read/write
```

The config directory contains metric, scoring profile, and source manifest configuration.

The data directory contains the processed dataset and generated outputs.

## Build containers

Build both services:

```bash
docker compose build
```

Build without cache:

```bash
docker compose build --no-cache
```

Build a single service:

```bash
docker compose build backend
docker compose build ui
```

## Start containers

Start both services and show logs:

```bash
docker compose up --build
```

Start in detached mode:

```bash
docker compose up --build -d
```

Check running services:

```bash
docker compose ps
```

Follow logs:

```bash
docker compose logs -f
```

Follow one service:

```bash
docker compose logs -f backend
docker compose logs -f ui
```

Stop services:

```bash
docker compose down
```

Stop services and remove volumes created by Compose:

```bash
docker compose down -v
```

## Verification checklist

After running:

```bash
docker compose up --build
```

Verify the backend is live:

```text
http://localhost:8000/health
```

Expected result:

```json
{
  "status": "ok",
  "service": "country-compare-api",
  "version": "0.1.0"
}
```

Verify the backend is ready:

```text
http://localhost:8000/ready
```

Expected ready behavior:

```text
HTTP 200 when the processed dataset exists and config validation passes.
HTTP 503 when the dataset or config is not ready.
```

Verify API docs are available when docs are enabled:

```text
http://localhost:8000/docs
```

Verify the UI is available:

```text
http://localhost:8501
```

Verify the UI can load metadata selectors such as countries, metrics, years, and profiles. In Compose mode, this confirms that the UI is calling the backend over HTTP.

## Health checks

The backend container health check uses:

```text
http://127.0.0.1:8000/health
```

The UI container health check uses:

```text
http://127.0.0.1:8501/_stcore/health
```

The Compose setup should wait for the backend to become healthy before starting the UI when `depends_on` is configured with a health condition.

## Makefile shortcuts

If the Makefile container targets are present, use:

```bash
make container-build
make container-up
make container-logs
make container-ps
make container-down
```

If using Podman with a Docker-compatible Compose command, the Makefile can be invoked with:

```bash
make container-up DOCKER=podman
```

## Local mode vs containerized HTTP mode

Local Streamlit mode:

```bash
python -m streamlit run country_compare/ui/app.py
```

In this mode, leave `COUNTRY_COMPARE_API_URL` unset. The UI calls the local service layer directly.

Local backend mode:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Local UI against local backend:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run country_compare/ui/app.py
```

Docker Compose mode:

```bash
docker compose up --build
```

In Compose mode, the UI should use:

```text
COUNTRY_COMPARE_API_URL=http://backend:8000
```

Do not use `http://localhost:8000` inside the UI container. Inside the UI container, `localhost` refers to the UI container itself, not the backend container.

## Data requirements

The backend readiness endpoint expects the processed canonical dataset to be available at the configured store path.

If `/ready` returns `503`, check:

1. the processed dataset exists
2. the `./data` directory is mounted into the containers
3. the backend and UI containers use the same relevant data/config paths
4. config validation passes against the dataset
5. scoring profiles reference valid metric IDs
6. metrics config matches the processed dataset

Useful command:

```bash
docker compose logs backend
```

## Troubleshooting

### Backend `/health` works but `/ready` returns `503`

The API process is alive, but the app is not ready to serve business requests.

Check:

```text
processed dataset exists
metrics config exists
scoring profiles config exists
config validates against the dataset
data mount points are correct
```

### UI opens but selectors are empty

The UI may be unable to reach the backend or the backend may not be ready.

Check:

```bash
docker compose logs ui
docker compose logs backend
```

Then verify:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8000/api/v1/metadata/countries
http://localhost:8000/api/v1/metadata/metrics
```

### UI container cannot reach backend

Confirm the UI container uses:

```text
COUNTRY_COMPARE_API_URL=http://backend:8000
```

Do not use:

```text
COUNTRY_COMPARE_API_URL=http://localhost:8000
```

inside Compose.

### Code changes are not reflected

Rebuild the images:

```bash
docker compose build
docker compose up
```

Or rebuild without cache:

```bash
docker compose build --no-cache
```

### Dependency changes are not reflected

Rebuild the images after changing `pyproject.toml` or dependency files:

```bash
docker compose build --no-cache
```

### Port already in use

If port `8000` or `8501` is already used locally, either stop the conflicting process or change the host-side port mapping in `docker-compose.yml`.

Example:

```yaml
ports:
  - "18000:8000"
```

Then access the backend at:

```text
http://localhost:18000
```

## Current limitations

This container setup intentionally does not include:

```text
production web server hardening
TLS termination
authentication
authorization
database service
object storage service
scheduled ingestion
dataset refresh API
config editing API
cloud deployment manifests
Kubernetes manifests
```

The backend API remains read-only in v0.1.

## Recommended validation before pushing

Run local checks:

```bash
python -m pytest
python -m ruff check country_compare tests scripts
python -m black --check country_compare tests scripts
python -m mypy country_compare
```

Build containers:

```bash
docker compose build
```

Run and verify manually:

```bash
docker compose up --build
```

Then check:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8501
```

For more details, see:

```text
docs/containerization.md
```