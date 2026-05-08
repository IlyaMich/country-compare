# Development Guide

This guide describes how to work on Country Compare without breaking the beta architecture.

## Repository layout

```text
src/country_compare/   Python package
tests/                 Test suite
scripts/               Utility scripts
config/                Metrics and scoring config
data/                  Data files and processed outputs
docs/                  Documentation
```

## Import rule

The package lives at:

```text
src/country_compare
```

Imports must use:

```python
import country_compare
```

Never use:

```python
import src.country_compare
```

## Where to make changes

### UI changes

Use:

```text
src/country_compare/ui/
```

Common areas:

```text
src/country_compare/ui/views/
src/country_compare/ui/components/
src/country_compare/ui/text.py
src/country_compare/ui/navigation.py
```

Prefer pure helper functions for dataframe shaping, summary extraction, and chart preparation so behavior can be unit-tested without launching Streamlit.

### API changes

Use:

```text
src/country_compare/api/
```

Keep routes thin. Route handlers should parse DTOs, call services/facade methods, and serialize responses.

Do not add write endpoints for `v0.1 beta`.

### Service changes

Use:

```text
src/country_compare/services/
```

Services should orchestrate application workflows. Avoid moving framework-specific code into services.

### Domain changes

Use:

```text
src/country_compare/comparison/
src/country_compare/prediction/
src/country_compare/scoring/
src/country_compare/data/
```

Domain modules should remain framework-neutral. They should not import FastAPI or Streamlit.

## Visualization guidance

For HTTP/container compatibility, prefer rebuilding charts in the Streamlit layer from JSON-safe returned tables.

Preferred UI components:

```python
st.bar_chart(...)
st.line_chart(...)
st.dataframe(...)
st.metric(...)
```

Avoid passing live matplotlib figure objects over HTTP.

## Adding dependencies

Keep dependencies minimal.

Before adding a new package, document:

- why it is needed
- whether it is runtime or dev-only
- where it is added in `pyproject.toml`
- Docker/CI implications

For beta visualization work, prefer existing Streamlit-native charting unless a new dependency is strongly justified.

## Quality commands

Run before merging:

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
docker compose build
```

## Manual verification

After meaningful UI/API/container changes, run:

```bash
docker compose up --build
```

Verify:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8501
```
