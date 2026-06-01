# Getting started

## Prerequisites

- Python 3.11.
- Docker and Docker Compose for containerized runs.
- A shell that can set environment variables.

## Local install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the Streamlit UI locally

Local mode does not require the FastAPI backend. The UI calls the in-process client, which calls services/facade directly.

```bash
country-compare ui
```

Alternative:

```bash
python -m streamlit run src/country_compare/ui/app.py
```

## Run the backend locally

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

Check it:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Open API docs when enabled:

```text
http://localhost:8000/docs
```

## Run the UI against the backend

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

Windows PowerShell:

```powershell
$env:COUNTRY_COMPARE_API_URL = "http://localhost:8000"
python -m streamlit run src/country_compare/ui/app.py
```

When the backend uses `COUNTRY_COMPARE_API_KEY`, set the same value for the UI process.

## Docker Compose quick start

```bash
docker compose up --build
```

Open:

```text
UI:      http://localhost:8501
Backend: http://localhost:8000
```

Stop:

```bash
docker compose down
```

## Optional LLM forecast quick start

The optional LLM service is disabled by default and should remain private. For local testing:

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

Typical local environment values:

```text
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=dev-token
MISTRAL_API_KEY=<local-secret>
MISTRAL_MODEL=mistral-large-latest
```

Check backend-to-LLM readiness:

```bash
curl http://localhost:8000/ready/llm
```

## First validation pass

```bash
country-compare validate-config
country-compare validate-data
python -m pytest
```

For a faster smoke pass:

```bash
python -m pytest tests/smoke
python -m pytest tests/integration/api
```
