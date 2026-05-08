# Architecture

Country Compare is structured around a service-oriented Python application with separate UI, API, domain, and data layers.

## High-level flow

```text
Streamlit UI
  -> CountryCompareClient
    -> LocalCountryCompareClient
      -> AppFacade / services
    -> HttpCountryCompareClient
      -> FastAPI backend
        -> AppFacade / services
  -> comparison, scoring, prediction, data, config modules
  -> processed canonical dataset
```

## Package layout

```text
src/
  country_compare/
    api/
    clients/
    cli/
    comparison/
    config/
    data/
    exports/
    metrics/
    output/
    pipelines/
    prediction/
    scoring/
    services/
    settings/
    ui/
    paths.py

config/
data/
docs/
scripts/
tests/
```

The package is imported as `country_compare`, not `src.country_compare`.

## Core boundaries

### UI layer

The Streamlit UI owns presentation behavior:

- selectors
- result panels
- quality and limitation panels
- export controls
- Streamlit-native charts
- local-vs-HTTP client selection

The UI should not duplicate domain logic.

### Client layer

The client layer provides a stable UI-facing interface.

- Local mode calls services in-process.
- HTTP mode calls FastAPI and reconstructs service-style result objects from JSON-safe response envelopes.

### API layer

The FastAPI backend is a read-only transport adapter.

Routes should:

1. parse request DTOs
2. call services/facade methods
3. serialize responses
4. map errors consistently

Routes should not contain comparison, scoring, prediction, or data-processing logic.

### Service layer

The service layer orchestrates application workflows and is the main integration boundary for API and UI callers.

Relevant modules include:

```text
country_compare.services.comparison_service
country_compare.services.prediction_service
country_compare.services.presentation_service
country_compare.services.facade
country_compare.services.results
country_compare.services.serialization
```

### Domain modules

Domain modules remain framework-neutral:

```text
comparison/
prediction/
data/
config/
scoring/
metrics/
pipelines/
```

These modules should not import Streamlit or FastAPI.

## Read-only backend boundary

The `v0.1 beta` API exposes read-only computation and metadata endpoints. It does not expose:

- config writes
- profile edits
- dataset refresh
- ingestion execution
- scheduled jobs
- authentication/authorization
- persistent server-side export creation

## Visualization strategy

Local Streamlit mode may have access to in-process presentation objects.

HTTP-backed/container mode receives JSON-safe result envelopes and table payloads. It does not receive live Python figure objects.

Therefore, HTTP/container visualizations are rebuilt in the Streamlit UI from returned tables or chart-ready payloads using container-friendly Streamlit-native components such as:

- `st.bar_chart`
- `st.line_chart`
- `st.dataframe`
- `st.metric`

This avoids transporting matplotlib objects over HTTP and keeps the backend API JSON-safe.
