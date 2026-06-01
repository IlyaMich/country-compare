# Optional LLM forecast service

The LLM forecast service is a separate private microservice under `services/llm_forecast_service/`. It is disabled by default and should never be exposed as a public unauthenticated endpoint.

## Purpose

`llm_forecast` performs a bounded adjustment on deterministic baseline forecasts. It is intended to add structured qualitative adjustment while preserving deterministic forecast foundations and explicit bounds.

It is not an authoritative forecast source. Treat all LLM-adjusted values as experimental and show warnings/diagnostics to users.

## Runtime architecture

```text
Country Compare backend
  -> bearer-token HTTP request
  -> private llm-forecast service
  -> provider API, currently Mistral-oriented
```

The backend only advertises `llm_forecast` in `/api/v1/metadata/prediction-methods` when all gates pass:

- backend feature flag enabled;
- service URL and token configured;
- private service reachable;
- `/v1/capabilities` succeeds;
- service reports structured-output support;
- service reports bounded-adjustment support.

## Local Compose run

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

Typical local configuration:

```text
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=dev-token
MISTRAL_API_KEY=<local-secret>
MISTRAL_MODEL=mistral-large-latest
```

Check backend readiness:

```bash
curl http://localhost:8000/ready/llm
curl http://localhost:8000/api/v1/metadata/prediction-methods
```

## Service endpoints

The private service exposes operational and versioned endpoints similar to:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service liveness. |
| `GET` | `/ready` | Provider/config readiness. |
| `GET` | `/v1/capabilities` | Feature/capability metadata used by backend gating. |
| `POST` | `/v1/forecast/adjust` | Bounded forecast-adjustment request. |
| `GET` | `/metrics` | Operational metrics when enabled and allowed. |

Use bearer-token auth for private endpoints. Protect metrics when running outside a fully trusted network.

## Safety and correctness requirements

- Preserve deterministic baseline as the foundation.
- Keep adjustments bounded and auditable.
- Require structured output; do not parse arbitrary prose as forecast data.
- Do not log prompts, provider keys, bearer tokens, or sensitive request bodies.
- Return diagnostics and warnings when adjustment is skipped or bounded.
- Fail closed: if capabilities/readiness are missing, the backend should not expose `llm_forecast`.

## Testing

From the service directory:

```bash
cd services/llm_forecast_service
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
cd ../..
```

From the repository root, run main-app tests that verify backend gating and HTTP client behavior:

```bash
python -m pytest tests/unit tests/integration/api tests/unit/clients
```

## Troubleshooting

### `llm_forecast` does not appear in the UI

Check:

1. backend has `COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true`;
2. backend has service URL/token configured through Compose or environment;
3. private service is running;
4. provider key/model are configured;
5. `/ready/llm` returns ready;
6. `/api/v1/metadata/prediction-methods` includes `llm_forecast`;
7. UI is using HTTP mode against the backend or has equivalent local config.

### `/ready/llm` returns not ready

Read backend and service logs. Common causes:

- missing service token;
- mismatched token between backend and service;
- missing provider API key;
- provider API unavailable;
- capabilities response missing required structured-output or bounded-adjustment flags.

### Forecast adjustment fails

The service should return structured errors without leaking secrets. Check request size/history limits, provider response shape, timeout settings, and whether fallback deterministic forecast is still returned by the backend.
