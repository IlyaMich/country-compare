# Manual QA checklist

Use this checklist before a release or after user-visible changes.

## Environment

- [ ] Fresh virtual environment can install `.[dev]`.
- [ ] `country-compare validate-config` passes.
- [ ] `country-compare validate-data` passes.
- [ ] `python -m pytest` passes or known skipped tests are documented.
- [ ] Docker build succeeds.

## Backend API

With backend running:

- [ ] `GET /health` returns process liveness.
- [ ] `GET /ready` returns ready with valid dataset/config.
- [ ] `GET /api/v1/metadata/dataset` returns expected counts and schema status.
- [ ] `GET /api/v1/metadata/countries` returns expected country list.
- [ ] `GET /api/v1/metadata/metrics` returns expected metric list, units, and categories.
- [ ] `GET /api/v1/metadata/profiles` returns scoring profiles.
- [ ] `GET /api/v1/metadata/prediction-methods` returns baseline methods and only gated optional methods.
- [ ] Response headers include `X-Request-ID`.
- [ ] Invalid metric/country/profile requests return stable error payloads.
- [ ] API-key protection works when `COUNTRY_COMPARE_API_KEY` is set.

## Comparison and scoring

- [ ] Single-metric comparison works for representative countries.
- [ ] Multi-metric comparison works and respects `higher_is_better`.
- [ ] Profile scoring works and surfaces profile metadata.
- [ ] Top-N limits are enforced.
- [ ] Warnings and diagnostics render in UI and API output.

## Prediction

- [ ] Single-metric forecast works with `linear_trend`.
- [ ] Fallback to `last_observed` works for sparse histories.
- [ ] Backtesting works for a representative country/metric.
- [ ] Predicted single-metric comparison works.
- [ ] Predicted profile comparison works.
- [ ] Predicted multi-metric comparison works.
- [ ] Forecast limitations are visible to users.

## UI local mode

- [ ] Run with `COUNTRY_COMPARE_API_URL` unset.
- [ ] Country/metric/profile selectors load.
- [ ] Comparison panels render tables/charts.
- [ ] Prediction panels render actuals, forecasts, warnings, and diagnostics.
- [ ] Exports are available.

## UI HTTP mode

- [ ] Run backend.
- [ ] Set `COUNTRY_COMPARE_API_URL=http://localhost:8000`.
- [ ] Repeat representative comparison/scoring/prediction flows.
- [ ] Confirm charts are rebuilt from JSON-safe payloads.
- [ ] Confirm protected backend works when API key is configured in both backend and UI.

## Optional LLM forecast

When enabled intentionally:

- [ ] LLM service runs on private network.
- [ ] `/ready/llm` returns ready.
- [ ] `/api/v1/metadata/prediction-methods` includes `llm_forecast`.
- [ ] UI exposes `llm_forecast` only when available.
- [ ] LLM-adjusted forecast includes diagnostics/warnings.
- [ ] Provider keys and tokens do not appear in logs, responses, or screenshots.

When disabled intentionally:

- [ ] `/ready/llm` returns not ready or disabled.
- [ ] `llm_forecast` is not advertised to the UI.

## Documentation

- [ ] README commands match working commands.
- [ ] `/docs` directory covers changed endpoints/env vars.
- [ ] Deployment docs mention readiness and read-only boundary.
- [ ] LLM docs mention private/token-protected/bounded/experimental behavior.
