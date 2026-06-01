# LLM Forecast Service

This service is the optional private microservice used by Country Compare's experimental `llm_forecast` prediction method. It performs bounded, structured forecast adjustments on top of deterministic baseline forecasts.

It is disabled by default and must not be exposed publicly.

## Responsibilities

- Accept forecast-adjustment requests from the Country Compare backend.
- Authenticate requests with a bearer token.
- Call the configured provider, currently Mistral-oriented in local examples.
- Require structured output.
- Enforce bounded adjustments.
- Return diagnostics/warnings when adjustment is skipped, rejected, bounded, or falls back.
- Expose health, readiness, capabilities, and metrics endpoints for private operational use.

## Non-goals

- It is not a public API.
- It is not a replacement for deterministic forecasting.
- It should not run ingestion, scoring, comparison, or dataset operations.
- It should not log secrets, provider prompts containing sensitive data, bearer tokens, or provider keys.

## Local setup

From the repository root, the easiest local run is the LLM Compose profile:

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
```

Typical local variables:

```text
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=true
COUNTRY_COMPARE_LLM_SERVICE_TOKEN=dev-token
MISTRAL_API_KEY=<local-secret>
MISTRAL_MODEL=mistral-large-latest
```

The backend will advertise `llm_forecast` only when it can reach this service and the service reports required capabilities.

## Expected private endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness. |
| `GET` | `/ready` | Provider/config readiness. |
| `GET` | `/v1/capabilities` | Capability metadata used by backend gating. |
| `POST` | `/v1/forecast/adjust` | Bounded adjustment endpoint. |
| `GET` | `/metrics` | Metrics, when enabled and allowed. |

## Development checks

```bash
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
```

From the repository root, also run the main app tests that verify backend gating and client behavior:

```bash
python -m pytest tests/unit tests/integration/api tests/unit/clients
```

## Operational guidance

- Keep the service on a private network.
- Use a strong shared token between backend and service.
- Configure provider keys through secrets management, not committed env files.
- Protect or disable metrics if the service runs outside a fully trusted network.
- Set timeouts and input limits to prevent long or expensive provider calls.
- Prefer fail-closed gating: if readiness/capabilities fail, the backend should omit `llm_forecast`.

## Troubleshooting

If `llm_forecast` is missing:

1. confirm the service container is running;
2. confirm token values match;
3. confirm provider key/model values are set;
4. call backend `/ready/llm`;
5. call backend `/api/v1/metadata/prediction-methods`;
6. inspect service logs for provider or structured-output errors.

If forecast adjustment fails, deterministic forecast behavior should still be available through baseline methods such as `linear_trend` and `last_observed`.
