# Country Compare v0.1 Beta Release Notes

## Status

`v0.1 beta` is the first beta checkpoint for the full local/API/containerized Country Compare application.

## Included

### Comparison workflows

- Single-metric country comparison.
- Multi-metric country comparison.
- Weighted/profile scoring workflows.
- Result summaries, detailed tables, and exports where available.

### Prediction workflows

- Single forecast.
- Multi-country forecast.
- Predicted comparison.
- Backtest.
- Prediction quality and limitations panels.
- Forecast and backtest visualizations where returned data supports them.

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

### Streamlit UI

- Local in-process mode.
- HTTP-backed mode.
- Streamlit-native charts reconstructed from returned tables in HTTP/container mode.
- Duplicate primary table display guard.
- Export controls preserved where supported.

### Container support

- Docker Compose split between backend and UI containers.
- Backend available on port `8000`.
- UI available on port `8501`.

### Packaging

- `/src` package layout.
- Package imports remain `country_compare`.

## Explicitly not included

`v0.1 beta` does not include:

- write API endpoints
- config editing endpoints
- scoring profile editing endpoints
- dataset refresh endpoints
- ingestion execution endpoints
- scheduled ingestion/processing
- authentication or authorization
- Kubernetes/cloud deployment files
- new prediction algorithms beyond the current baseline methods

## Known limitations

- Forecasts are baseline statistical projections, not guarantees.
- Sparse or stale historical data can reduce prediction reliability.
- Backtest performance does not guarantee future forecast performance.
- HTTP/container mode visualizations depend on returned table shapes.
- Some result tables may not be chartable; in that case, the UI should preserve table output and show explanatory text.
- API is intentionally read-only for this beta.

## Validation checklist

Before tagging or publishing this beta, run:

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
docker compose build
```

Then run:

```bash
docker compose up --build
```

Verify:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8501
```

Also verify local UI mode:

```bash
unset COUNTRY_COMPARE_API_URL
country-compare ui
```

And HTTP-backed UI mode:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
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
