# Manual QA Checklist

Use this checklist before tagging or publishing `v0.1 beta`.

## 1. Baseline checks

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
docker compose build
```

## 2. CLI validation

```bash
country-compare validate-config
country-compare validate-data
```

Expected:

- config validation passes
- data validation passes
- no unexpected import/path errors

## 3. Local UI mode

Linux/macOS:

```bash
unset COUNTRY_COMPARE_API_URL
country-compare ui
```

Windows PowerShell:

```powershell
Remove-Item Env:COUNTRY_COMPARE_API_URL -ErrorAction SilentlyContinue
country-compare ui
```

Verify:

- UI opens
- selectors load
- comparison page works
- prediction page works
- no `src.country_compare` import errors

## 4. HTTP-backed UI mode

Start backend:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Start UI:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

Verify:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8501
```

Expected:

- `/health` returns OK
- `/ready` behaves correctly
- UI uses HTTP mode
- metadata selectors load
- result pages work

## 5. Docker Compose mode

```bash
docker compose up --build
```

Verify:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8501
```

Expected:

- backend starts
- UI starts
- UI can call backend
- container logs show no visualization-related errors

## 6. Comparison workflow checks

### Single-metric comparison

Verify in local and HTTP/container modes:

- run comparison with at least two countries
- summary panel renders
- chart renders when country/value data is available
- detailed main table renders
- export controls still work where available

### Multi-metric comparison

Verify in HTTP/container mode:

- run comparison with multiple countries and metrics
- useful chart appears when returned data is chartable
- clear explanation appears if data is not chartable
- detailed table remains visible
- no duplicate primary table display

### Weighted/profile scoring

Verify in HTTP/container mode:

- run scoring/profile comparison
- score/ranking visual appears when score/rank data is available
- detailed table remains visible
- exports still work

## 7. Prediction workflow checks

### Single forecast

Verify in local and HTTP/container modes:

- forecast runs
- quality/limitations panel is visible
- actual-vs-forecast chart appears when chart-ready data is available
- forecast table remains visible
- exports still work

### Multi-country forecast

Verify in HTTP/container mode:

- multi-country forecast runs
- useful forecast visualization appears when chart-ready data is available
- diagnostics/warnings remain visible
- detailed table remains visible

### Predicted comparison

Verify in HTTP/container mode:

- predicted single-metric comparison works
- predicted multi-metric comparison works where supported
- predicted profile comparison works
- ranked summary is visible
- bar chart is visible when ranking/value data is available
- quality warnings appear before ranking output
- detailed table remains visible
- exports still work

### Backtest

Verify in HTTP/container mode:

- backtest runs
- quality/evaluation context appears
- error metrics render
- actual-vs-predicted chart appears when returned data has usable columns
- detailed actual-vs-predicted table remains visible

## 8. Final beta checks

Confirm:

- local mode works
- HTTP-backed mode works
- Docker Compose mode works
- no write endpoints were added
- no auth/cloud/Kubernetes/ingestion scheduling work was added
- package imports remain `country_compare`
- docs are current
- release notes are current
