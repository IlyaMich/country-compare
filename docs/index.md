# Country Compare documentation

This directory documents the current Country Compare implementation: the Streamlit UI, service/domain core, read-only FastAPI backend, canonical dataset contract, prediction workflows, optional private LLM forecast service, Docker/Compose runtime, testing, and deployment.

## Documentation map

| File | Purpose |
| --- | --- |
| `getting_started.md` | Fast local and Docker start instructions. |
| `user_guide.md` | User-facing UI workflows and exports. |
| `architecture.md` | Layering, boundaries, service flow, and read-only API policy. |
| `api.md` | FastAPI endpoints, request shapes, response envelopes, auth, and examples. |
| `configuration.md` | Config files, environment variables, runtime settings, and safe defaults. |
| `containerization.md` | Dockerfiles, Compose files, profiles, local smoke checks. |
| `deployment_api.md` | Production-oriented backend deployment guidance. |
| `data_contract.md` | Canonical long-format dataset schema and validation expectations. |
| `dataset_replacement.md` | How to replace or refresh processed datasets. |
| `prediction.md` | Forecasting, backtesting, predicted comparisons, quality guidance. |
| `prediction_methods.md` | Method registry, baseline methods, optional `llm_forecast`, adding methods. |
| `llm_forecast_service.md` | Private LLM adjustment service setup, endpoints, secrets, tests, troubleshooting. |
| `testing.md` | Unit, integration, smoke, data correctness, UI/API/client, LLM checks. |
| `manual_qa.md` | Manual QA checklist before a release. |
| `demo_walkthrough.md` | Demo flow for UI, API, forecasts, exports. |
| `troubleshooting.md` | Common local, API, data, UI, Docker, and LLM issues. |
| `release_notes_v0_1_beta.md` | Current implementation notes retained for release history. |

## Current architecture in one screen

```text
raw data / source manifests
  -> pipeline acquisition and processing
  -> canonical long-format metrics dataset
  -> data access + config validation
  -> comparison / scoring / prediction domain modules
  -> services/facade
  -> local client or HTTP client
  -> Streamlit UI
```

Containerized HTTP mode:

```text
Streamlit UI container
  -> HTTP client
  -> FastAPI backend container
  -> country_compare.services
  -> framework-neutral domain modules
  -> processed dataset/config
```

Optional LLM runtime:

```text
FastAPI backend
  -> HTTP + bearer token
  -> private llm-forecast service
  -> provider API
```

## Invariants every doc and implementation should preserve

- The backend API is read-only.
- Business logic belongs in domain and service layers, not in route handlers or Streamlit views.
- The UI calls through the client abstraction.
- Local UI mode and HTTP-backed UI mode should be behaviorally equivalent.
- HTTP responses must be JSON-safe.
- Canonical data remains long-format with one row per `country_code + metric_id + year`.
- LLM forecasts remain optional, private, token-protected, bounded, and experimental.
