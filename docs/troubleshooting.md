# Troubleshooting

This guide covers common issues in `v0.1 beta`.

## Import errors after `/src` migration

### Symptom

```text
ModuleNotFoundError: No module named 'country_compare'
```

### Fix

Install the package in editable mode:

```bash
python -m pip install -e ".[dev]"
```

Run commands from the repository root.

## Accidental `src.country_compare` imports

### Symptom

Imports work locally in one environment but fail in tests, Docker, or installed-package mode.

### Fix

Search for bad imports:

```bash
git grep "src.country_compare"
```

Replace with:

```python
import country_compare
```

or:

```python
from country_compare...
```

## Streamlit path error

### Symptom

Old command fails:

```bash
python -m streamlit run country_compare/ui/app.py
```

### Fix

Use the `/src` filesystem path:

```bash
python -m streamlit run src/country_compare/ui/app.py
```

Or use the CLI:

```bash
country-compare ui
```

## UI unexpectedly uses local mode

### Symptom

The UI does not call the backend.

### Fix

Set:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000
```

Then run:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

## UI cannot reach backend

### Checks

Confirm backend is running:

```bash
curl http://localhost:8000/health
```

Confirm readiness:

```bash
curl http://localhost:8000/ready
```

In Docker Compose, the UI should usually use:

```text
COUNTRY_COMPARE_API_URL=http://backend:8000
```

not `localhost`, because `localhost` inside the UI container means the UI container itself.

## Backend not ready

### Symptom

`/ready` returns not ready or 503.

### Causes

- processed dataset missing
- config validation failure
- metric/profile config does not match dataset
- data path/store configuration issue

### Fix

Run:

```bash
country-compare validate-config
country-compare validate-data
```

Then inspect the readiness response body for warnings.

## Docker port conflict

### Symptom

Docker Compose fails to bind ports.

### Fix

Check for processes using:

```text
8000
8501
```

Stop the conflicting process or change Compose port mappings.

## Missing charts in HTTP/container mode

### Explanation

HTTP mode receives JSON-safe table payloads, not live Python figure objects. The UI rebuilds charts from returned table data.

Charts require usable columns such as:

```text
country/name label
year
metric/series
value/score/forecast/predicted
```

If the returned result table is not chartable, the UI should preserve the table and show a clear explanation instead of failing.

## Duplicate tables or charts

### Expected behavior

The main result table should display once. Extra tables should not duplicate the primary `main` table.

If duplicates appear, inspect UI result panel logic and HTTP reconstruction behavior.

## Export controls missing

### Checks

- confirm the result object has presentation/export support
- confirm HTTP presentation adapter is available in HTTP-backed mode
- confirm the result has table data to export
- check browser and backend logs for errors

## Mypy, ruff, or black fail on paths

Use `/src` paths:

```bash
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
```
