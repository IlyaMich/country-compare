# Testing Guide

Country Compare uses unit, integration, smoke, and manual QA checks.

## Full test and quality suite

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
docker compose build
```

## Focused test commands

### UI helper tests

```bash
python -m pytest tests/unit/ui
```

Use these for dataframe shaping, result panel summaries, quality helpers, and Streamlit-independent logic.

### Client tests

```bash
python -m pytest tests/unit/clients
```

Use these when changing local/HTTP client behavior or HTTP result reconstruction.

### API tests

```bash
python -m pytest tests/integration/api
```

Use these when changing FastAPI routes, schemas, serialization, or error mapping.

### Full pytest only

```bash
python -m pytest
```

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

### HTTP client changes

Test that JSON-safe API envelopes reconstruct into the expected local-style result objects.

Important cases:

- main table present
- extra tables present
- warnings/messages preserved
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

### Prediction changes

Test:

- sparse data behavior
- fallback diagnostics
- failed series handling
- backtest error metrics
- chart-ready table construction
- warning propagation

### Comparison/scoring changes

Test:

- single-metric comparison
- multi-metric comparison
- profile scoring
- rank/score behavior
- missing data behavior
- chart helper behavior

## Docker validation

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

## Manual QA

Use [manual_qa.md](manual_qa.md) before tagging or publishing the beta.
