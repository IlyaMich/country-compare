# Getting Started

This guide gets a new developer from a fresh checkout to a running `v0.1 beta` application.

## Repository

```bash
git clone https://github.com/IlyaMich/country-compare.git
cd country-compare
git checkout develop
```

## Install for local development

```bash
python -m pip install -e ".[dev]"
```

The project uses a `/src` package layout. Editable installation is recommended so all entrypoints resolve the installed package correctly.

## Validate configuration and data

```bash
country-compare validate-config
country-compare validate-data
```

These commands should pass before using the UI, API, or Docker Compose mode.

## Run local Streamlit UI mode

Local mode uses in-process services and does not require the FastAPI backend.

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

Alternative direct Streamlit command:

```bash
python -m streamlit run src/country_compare/ui/app.py
```

## Run HTTP-backed UI mode

Start the backend:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Then start the UI with the backend URL configured:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

Open:

```text
http://localhost:8501
```

## Run Docker Compose mode

```bash
docker compose up --build
```

Open:

```text
Backend health:    http://localhost:8000/health
Backend readiness: http://localhost:8000/ready
Streamlit UI:      http://localhost:8501
```

## Run checks

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
docker compose build
```

## Import rule

Use:

```python
from country_compare.services.facade import AppFacade
```

Do not use:

```python
from src.country_compare.services.facade import AppFacade
```
