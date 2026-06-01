# Prediction methods

Prediction methods are exposed to callers through runtime metadata:

```text
GET /api/v1/metadata/prediction-methods
```

The UI should use this metadata rather than hard-coding method availability. This is especially important for optional gated methods such as `llm_forecast`.

## Baseline methods

### `linear_trend`

Fits a simple deterministic trend to historical observations and extends it over the requested horizon. It is useful as an interpretable baseline but can overfit short histories or extrapolate through structural breaks.

### `last_observed`

Carries forward the last available observation. It is useful as a conservative fallback for sparse histories.

## Optional `llm_forecast`

`llm_forecast` is disabled by default. It is exposed only when the backend can reach a private token-protected LLM service that reports required capabilities.

Use it as a bounded adjustment over deterministic baselines, not as a standalone authority.

## Fallback behavior

Prediction requests should specify a fallback method. Fallbacks are used when:

- the requested method lacks enough history;
- method validation fails;
- external optional services are unavailable;
- provider/capability checks fail;
- bounded adjustment is rejected or skipped.

## Adding a method

1. Implement deterministic or bounded logic in `country_compare.prediction` or the private service, depending on method type.
2. Add validation for method-specific parameters.
3. Add fallback behavior for sparse history.
4. Add diagnostics/warnings for low-quality inputs.
5. Wire through prediction services/facade.
6. Update API schemas and client methods if the method is externally selectable.
7. Update UI selector/help text through runtime metadata.
8. Add tests for method behavior, fallback, diagnostics, API serialization, and client round-trip.
9. Update this document and `prediction.md`.

## Do not

- Do not expose a method in the UI unless it is available through `/api/v1/metadata/prediction-methods`.
- Do not let optional provider failures crash unrelated deterministic workflows.
- Do not hide forecast warnings from users.
- Do not return non-JSON-safe prediction payloads through the API.
