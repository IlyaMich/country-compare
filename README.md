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

The project is designed around a stable canonical data contract so ingestion, comparison, prediction, UI, and exports remain modular.

## Screenshots

TODO

### Comparison workflow

![Comparison workflow placeholder](screenshot-path)

### Prediction workflow

![Prediction workflow placeholder](screenshot-path)

### Export-first result handling

![Exports placeholder](screenshot-path)

## Project status

The current implementation includes:

- canonical data contract and validation
- manifest-driven data processing pipeline
- local and remote source acquisition support
- comparison and weighted-score modules
- prediction and backtesting modules
- Streamlit UI
- reusable export helpers
- golden demo dataset and walkthrough

The project is still pre-v1. APIs and UI flows may change before `v0.1.0`.

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
services
        ↓
Streamlit UI + exports
```

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
  comparison/        # single- and multi-metric comparison workflows
  config/            # config models, loaders, and validators
  data/              # canonical contract, validation, access, stores, ingestion
  exports/           # reusable CSV / JSON / Markdown export helpers
  metrics/           # filtering and normalization helpers
  pipelines/         # processing engine, acquisition, manifests, audit, publish
  prediction/        # forecasting, backtesting, comparison bridge, visualization data
  scoring/           # weighted-score workflows
  services/          # app-facing orchestration and result models
  settings/          # centralized application settings
  ui/                # Streamlit app, views, state, components

config/              # metrics, scoring profiles, source manifests, demo config
data/examples/       # golden demo dataset
docs/                # walkthroughs and screenshots
scripts/             # demo and operational scripts
tests/               # unit, integration, and smoke tests
```

## Installation

Clone the repository:

```bash
git clone https://github.com/IlyaMich/country-compare.git
cd country-compare
```

Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install with development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the app

Start the Streamlit UI:

```bash
country-compare ui
```

Or run Streamlit directly:

```bash
python -m streamlit run country_compare/ui/app.py
```

Streamlit apps are normally launched with `streamlit run` or `python -m streamlit run`, which starts a local app server in the browser.

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

Run lint and formatting checks:

```bash
python -m ruff check country_compare tests scripts/demo_product_flow.py
python -m black --check country_compare tests scripts/demo_product_flow.py
```

Format locally:

```bash
python -m black country_compare tests scripts/demo_product_flow.py
python -m ruff check country_compare tests scripts/demo_product_flow.py --fix
```

## Data workflow

The preferred data workflow is manifest-driven:

```text
raw files
  → source manifest
  → processing pipeline
  → canonical dataframe validation
  → parquet publication
  → app/services/UI
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
python -m ruff check country_compare tests scripts/demo_product_flow.py
python -m black --check country_compare tests scripts/demo_product_flow.py
```
