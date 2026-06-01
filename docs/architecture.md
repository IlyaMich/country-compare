# Architecture

Country Compare is organized as a layered application. The center of the project is framework-neutral domain and service code. Streamlit and FastAPI are adapters around that core.

## High-level flow

```text
raw source files / source manifests
  -> acquisition and processing pipeline
  -> canonical long-format metrics dataset
  -> data access + configuration
  -> comparison / scoring / prediction domain modules
  -> services/facade
  -> local client or HTTP client
  -> Streamlit UI
```

## Layer responsibilities

### `country_compare.ui`

Owns presentation only:

- selectors and user inputs;
- result panels;
- forecast quality and limitation panels;
- export controls;
- Streamlit-native charts;
- local vs HTTP client selection.

The UI must not duplicate comparison, scoring, prediction, data loading, config parsing, or pipeline logic.

### `country_compare.clients`

Provides a stable UI-facing interface.

- Local client calls services/facade in-process.
- HTTP client calls the FastAPI backend and reconstructs service-style result objects from JSON-safe response envelopes.

When a user-facing workflow is added, both clients should stay behaviorally equivalent.

### `country_compare.api`

The FastAPI backend is a read-only transport adapter. It should:

1. parse request DTOs;
2. enforce configured limits;
3. call services/facade methods;
4. serialize results into JSON-safe envelopes;
5. map expected domain/service errors to stable error payloads;
6. log unexpected failures server-side without leaking internals to clients.

Routes must not contain comparison, scoring, prediction, ingestion, data refresh, or config-editing logic.

`country_compare.api.main:create_app()` reads `ApiSettings`, configures logging, request IDs, optional API-key enforcement, OpenAPI security metadata, optional CORS, exception handlers, metrics, and route inclusion.

### `country_compare.services`

The service layer is the main integration boundary for UI and API callers. It orchestrates domain workflows and returns structured result objects with:

- request metadata;
- summaries;
- diagnostics;
- warnings/messages;
- tables;
- chart-ready payloads;
- export-friendly data.

Services must remain framework-neutral: no FastAPI request objects and no Streamlit calls.

### Domain packages

Framework-neutral packages include:

```text
comparison/
prediction/
data/
config/
scoring/
metrics/
pipelines/
```

Keep deterministic computation, validation, config parsing, data loading, and transformations here.

### Optional LLM service

The LLM forecast service is a separate private service under `services/llm_forecast_service`. It is token-protected and only performs bounded forecast adjustments on top of deterministic baselines. It is disabled by default and should not be exposed publicly.

## Read-only API boundary

Allowed backend API responsibilities:

- metadata reads;
- readiness validation;
- comparison computation;
- weighted scoring computation;
- prediction computation;
- backtesting computation;
- JSON-safe result serialization.

Not allowed in the current backend API:

- ingestion runs;
- dataset refresh;
- config writes;
- scoring profile writes;
- server-side persistent export creation;
- pipeline execution;
- user authentication/authorization beyond optional API key.

## Serialization boundary

HTTP mode cannot transmit live Python objects such as `pandas.DataFrame`, matplotlib figures, numpy scalars, `pd.NA`, or timestamps directly. API serialization converts them into JSON-safe values and table payloads. The UI rebuilds tables and charts from the JSON response.

## Request and logging boundary

Every API response should include `X-Request-ID`. An inbound `X-Request-ID` is accepted and propagated. Access logs should contain request id, method, path, status, and duration. Unexpected exceptions should include stack traces in server logs while returning sanitized client responses.
