# Containerization

Country Compare supports a Docker Compose setup with separate backend and UI containers.

## Services

Typical Compose services:

```text
backend
ui
llm-forecast optional, profile-gated
```

### Backend container

Responsibilities:

- run FastAPI
- expose `/health`
- expose `/ready`
- expose read-only `/api/v1` business endpoints
- call application services and return JSON-safe payloads

Backend command shape:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

### UI container

Responsibilities:

- run Streamlit
- call the backend through `COUNTRY_COMPARE_API_URL`
- render tables, summaries, charts, quality panels, and export controls

Streamlit path under `/src` layout:

```bash
python -m streamlit run src/country_compare/ui/app.py --server.address=0.0.0.0 --server.port=8501
```

## Optional LLM forecast service

The `llm-forecast` service is disabled by default and only starts with the `llm` Compose profile.

```bash
docker compose --profile llm up --build
```

## Run Docker Compose

```bash
docker compose up --build
```

Open:

```text
Backend health:    http://localhost:8000/health
Backend readiness: http://localhost:8000/ready
Streamlit UI:      http://localhost:8501
```

## HTTP-backed visualization behavior

The UI container talks to the backend over HTTP.

The backend returns JSON-safe data, not live Python figure objects. Therefore charts in container mode are reconstructed inside Streamlit from returned tables and chart-ready payloads.

This is intentional because it keeps the backend API portable, JSON-safe, and container-friendly.

## Local split mode

You can also run backend and UI separately without Compose.

Backend:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

UI:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

## Common checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Then verify the UI:

```text
http://localhost:8501
```

## Common issues

### Port conflicts

If ports are already in use, stop the conflicting process or adjust Compose port mappings.

Default ports:

```text
8000 backend
8501 Streamlit UI
```

### Backend not ready

Check:

```text
http://localhost:8000/ready
```

Readiness can fail if data or config validation fails.

### UI cannot call backend

Confirm `COUNTRY_COMPARE_API_URL` is set inside the UI container to the backend service URL, typically:

```text
http://backend:8000
```

### Missing charts in HTTP mode

Charts require chartable result data. If the returned table lacks usable label/year/value columns, the UI should preserve tables and show explanatory text rather than failing.


## Public-beta backend hardening

The backend and UI images install the package in production mode and run as a non-root `app` user. The backend honors a platform-provided `PORT` environment variable, keeps `/health` as the container healthcheck target, and should be deployed with processed data and config mounted read-only for API-only deployments.