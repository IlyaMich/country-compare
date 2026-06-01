# Development guide

## Environment

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Import rule

Use package imports:

```python
import country_compare
```

Do not import from `src.country_compare`.

## Layering rules

- Domain modules must not import FastAPI or Streamlit.
- Services must be framework-neutral.
- API routes should parse/validate/call/serialize only.
- UI should call through `country_compare.clients`.
- HTTP responses must be JSON-safe.
- The current backend API must stay read-only.

## Adding a read-only API workflow

1. Implement domain logic in the relevant framework-neutral package.
2. Add orchestration in `country_compare.services` and facade methods.
3. Add or update result models and serialization helpers.
4. Add API schemas under `country_compare.api.schemas`.
5. Add a route under `country_compare.api.routes`.
6. Enforce `ApiSettings` limits early.
7. Wire local and HTTP clients.
8. Update UI only through the client abstraction.
9. Add service/domain, API, HTTP-client, and UI tests as applicable.
10. Run full checks.

## Adding a UI feature

- Keep Streamlit code presentation-oriented.
- Do not call domain modules directly from Streamlit views.
- Depend on JSON-safe response fields in HTTP mode.
- Add UI unit tests and at least one smoke/manual check.

## Adding a prediction method

1. Implement deterministic behavior in `country_compare.prediction`.
2. Add validation, fallback, and diagnostics for sparse histories.
3. Wire through services/facade and clients.
4. Update prediction method metadata.
5. Add API/client/UI tests if it is user-facing.
6. Document limitations in `prediction_methods.md` and `prediction.md`.

## Main checks

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
```

## LLM service checks

```bash
cd services/llm_forecast_service
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
cd ../..
```

## Container checks

```bash
docker compose build
docker compose --profile llm build llm-forecast
```

## Before opening a PR or tagging a release

- Config validation passes.
- Data validation passes when data/config changed.
- Main test/lint/format/type checks pass.
- LLM service checks pass when LLM code changed.
- Docker builds pass when container/runtime files changed.
- `/health`, `/ready`, and representative API calls pass.
- Manual QA relevant to the changed surface is complete.
