# Containerization

Country Compare supports a normal backend + UI Docker Compose stack and an optional LLM service profile.

## Default stack

```bash
docker compose up --build
```

Local URLs:

```text
Backend: http://localhost:8000
UI:      http://localhost:8501
```

The UI container talks to the backend through the Compose network using:

```text
COUNTRY_COMPARE_API_URL=http://backend:8000
```

Stop the stack:

```bash
docker compose down
```

## Build-only checks

```bash
docker compose build
docker compose --profile llm build llm-forecast
```

## Backend-only smoke check

The repository includes a backend container smoke script. Use it in CI or locally after the backend container is running:

```bash
python scripts/smoke_api_container.py --base-url http://localhost:8000
```

The smoke script should wait for `/health` and `/ready`, then exercise representative metadata and business endpoints.

## Optional LLM profile

The LLM service is disabled in the default stack. For local LLM testing:

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

Typical local secrets/config:

```text
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=dev-token
MISTRAL_API_KEY=<local-secret>
MISTRAL_MODEL=mistral-large-latest
```

The LLM service should stay private on the Compose network. Do not publish it to the public internet.

## Readiness checks

Backend:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Backend-to-LLM readiness:

```bash
curl http://localhost:8000/ready/llm
```

UI:

```text
http://localhost:8501
```

## API key in containers

When setting `COUNTRY_COMPARE_API_KEY` on the backend, provide the same key to the UI container so the HTTP client can authenticate.

## Persistent data

The backend reads the processed dataset packaged or mounted into the container. Data updates and ingestion should be run outside the read-only API process, then published as validated processed artifacts.

## Troubleshooting

- If the UI loads but shows API connection errors, check `COUNTRY_COMPARE_API_URL` and backend readiness.
- If `/ready` returns `503`, inspect dataset existence, schema validity, manifest status, and config validation details.
- If `llm_forecast` does not appear, check `/ready/llm`, the backend feature flag, service token, provider key, and `/v1/capabilities` in the private service.
- If container smoke tests time out, increase wait time only after checking backend logs for config/data validation failures.
