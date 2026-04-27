# Country Compare

Country Compare is a Python + Streamlit application for comparing countries across economic, health, governance, and social metrics.

It turns raw public-data-style inputs into a canonical long-format dataset, then supports:

- single-metric country comparison
- multi-metric comparison
- weighted scoring profiles
- baseline metric forecasting
- predicted comparisons
- backtesting
- diagnostics and quality panels
- CSV, JSON, and Markdown exports
- a read-only FastAPI backend for UI/backend separation

The project is designed around a stable canonical data contract so ingestion, comparison, prediction, API, UI, and exports remain modular.

## Project status

The current implementation includes:

- canonical data contract and validation
- manifest-driven data processing pipeline
- local and remote source acquisition support
- comparison and weighted-score modules
- prediction and backtesting modules
- app-facing service/facade layer
- read-only FastAPI backend
- Streamlit UI with local and HTTP-backed client modes
- Docker Compose split for backend and UI containers
- reusable export helpers
- golden demo dataset and walkthrough
- unit, integration, smoke, and API tests

The project is still pre-v1. APIs and UI flows may change before a stable v1 release.

## Architecture

```text
raw source files / source manifests
        ↓
processing pipeline
        ↓
canonical long-format metric dataset
        ↓
data access + config
        ↓
comparison / scoring / prediction
        ↓
services / facade
        ↓
local client or HTTP client
        ↓
Streamlit UI
```

Containerized mode uses this runtime shape:

```text
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

The backend API is intentionally a transport adapter. Business logic remains in the existing service/domain layers.

## Canonical dataset contract

The canonical dataset uses one row per:

```text
country_code + metric_id + year
```

Required columns include:

```text
country_code
country_name
metric_id
metric_name
value
year
unit
source_name
source_url
higher_is_better
category
```

Optional columns include:

```text
dataset_version
region
income_group
notes
```

## Repository layout

```text
country_compare/
  api/                # FastAPI app, schemas, routes, and API serialization
  clients/            # UI-facing local/HTTP client abstraction
  cli/                # CLI entrypoints
  comparison/         # single- and multi-metric comparison workflows
  config/             # config models, loaders, and validators
  data/               # canonical contract, validation, access, stores, ingestion
  exports/            # reusable CSV / JSON / Markdown export helpers
  metrics/            # filtering and normalization helpers
  output/             # charts and output helpers
  pipelines/          # processing engine, acquisition, manifests, audit, publish
  prediction/         # forecasting, backtesting, comparison bridge, visualization data
  scoring/            # weighted-score workflows
  services/           # app-facing orchestration and result models
  settings/           # centralized application settings
  ui/                 # Streamlit app, views, state, components

config/               # metrics, scoring profiles, source manifests, demo config
data/examples/        # golden demo dataset
docs/                 # walkthroughs and API docs
notebooks/            # exploratory notebooks
scripts/              # demo and operational scripts
tests/                # unit, integration, and smoke tests
```

## Installation

Clone the repository:

```bash
git clone https://github.com/IlyaMich/country-compare.git
cd country-compare
```

Create and activate a virtual environment.

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install with development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the Streamlit UI locally

Start the Streamlit UI through the CLI:

```bash
country-compare ui
```

Or run Streamlit directly:

```bash
python -m streamlit run country_compare/ui/app.py
```

When `COUNTRY_COMPARE_API_URL` is not set, the UI uses local in-process services directly. This is the default local development mode.

## Run the FastAPI backend locally

Start the backend API:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Useful backend URLs:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8000/docs
```

## Run the Streamlit UI against a local backend

In one terminal, start the backend:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

In another terminal, start the UI in HTTP-backed mode:

Windows PowerShell:

```powershell
$env:COUNTRY_COMPARE_API_URL = "http://localhost:8000"
python -m streamlit run country_compare/ui/app.py
```

macOS/Linux:

```bash
export COUNTRY_COMPARE_API_URL=http://localhost:8000
python -m streamlit run country_compare/ui/app.py
```

Selection rule:

```text
COUNTRY_COMPARE_API_URL unset -> local UI client
COUNTRY_COMPARE_API_URL set   -> HTTP UI client
```

## Run with Docker Compose

Build and start both services:

```bash
docker compose up --build
```

The backend is available at:

```text
http://localhost:8000
```

Useful backend checks:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8000/docs
```

The Streamlit UI is available at:

```text
http://localhost:8501
```

In Compose mode, the UI is configured with:

```text
COUNTRY_COMPARE_API_URL=http://backend:8000
```

That means the Streamlit container calls the FastAPI backend over HTTP instead of using the local service layer directly.

The Compose setup mounts local project config and data into both containers:

```text
./config -> /app/config
./data   -> /app/data
```

Stop the containers:

```bash
docker compose down
```

For more details, see:

```text
docs/containerization.md
```

## API overview

The backend API is read-only in v0.1.

Operational endpoints:

```text
GET /health
GET /ready
```

Metadata endpoints:

```text
GET /api/v1/metadata/dataset
GET /api/v1/metadata/countries
GET /api/v1/metadata/metrics
GET /api/v1/metadata/years
GET /api/v1/metadata/profiles
```

Comparison endpoints:

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
```

See the full API reference:

```text
docs/api.md
```

## Read-only v0.1 boundary

Allowed in the backend API:

- metadata reads
- dataset/config readiness validation
- comparison computation
- weighted scoring computation
- prediction computation
- backtesting computation
- JSON-safe result serialization

Deferred from the v0.1 API:

- config editing
- scoring profile editing
- dataset refresh
- ingestion runs
- pipeline execution
- scheduled processing runs
- server-side persistent export generation
- authentication/authorization

Do not add write endpoints such as:

```text
POST /api/v1/ingestion/run
POST /api/v1/data/refresh
POST /api/v1/config/metrics
POST /api/v1/config/scoring-profiles
PUT  /api/v1/...
DELETE /api/v1/...
```

## Run the golden demo

The deterministic golden demo uses only checked-in files.

```bash
python scripts/demo_product_flow.py
```

Expected output includes:

```text
Golden demo completed successfully.
Input rows: 64
Countries: 4
Metrics: 4
```

Generated outputs are written to:

```text
data/exports/golden_demo/
```

Expected files:

```text
single_metric_comparison.csv
multi_metric_comparison.csv
weighted_score.csv
forecast_table.csv
predicted_single_metric_comparison.csv
diagnostics.json
summary.md
```

See the full walkthrough:

```text
docs/demo_walkthrough.md
```

## CLI commands

The package exposes a `country-compare` command.

Useful commands:

```bash
country-compare ui
country-compare validate-config
country-compare validate-data
country-compare update-data --manifest config/source_manifests/world_bank_real_data.yaml
```

## Testing and quality checks

Run the full test suite:

```bash
python -m pytest
```

Run focused test groups:

```bash
python -m pytest tests/unit
python -m pytest tests/integration
python -m pytest tests/smoke
```

Run formatting, linting, and type checks:

```bash
python -m black --check country_compare tests scripts
python -m ruff check country_compare tests scripts
python -m mypy country_compare
```

Format locally:

```bash
python -m black country_compare tests scripts
python -m ruff check country_compare tests scripts --fix
```

Build containers:

```bash
docker compose build
```

Recommended full local verification before pushing:

```bash
python -m pytest
python -m ruff check country_compare tests scripts
python -m black --check country_compare tests scripts
python -m mypy country_compare
docker compose build
```

If you use the Makefile:

```bash
make check-strict
make container-build
```

## Data workflow

The preferred data workflow is manifest-driven:

```text
raw files
  → source manifest
  → processing pipeline
  → canonical dataframe validation
  → parquet publication
  → app/services/API/UI
```

The app should consume the processed canonical dataset rather than raw source files.

## Prediction notes

The prediction module currently provides baseline forecasting methods such as:

- last observed value
- linear trend
- moving average

Prediction outputs include diagnostics and quality panels. Treat forecasts as baseline statistical projections, not guarantees. Sparse histories, stale data, methodology changes, or external shocks can make forecasts unreliable.

## Export behavior

Country Compare supports export-first result handling:

- result tables as CSV
- diagnostics as JSON
- summaries as Markdown

Exports are available from the golden demo script and from UI result panels.

## Development workflow

Recommended loop:

```bash
python -m pytest
python -m ruff check country_compare tests scripts
python -m black --check country_compare tests scripts
python -m mypy country_compare
```