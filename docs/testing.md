# Testing and validation

## Full main application checks

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
```

## Focused test groups

```bash
python -m pytest tests/unit
python -m pytest tests/unit/ui
python -m pytest tests/unit/clients
python -m pytest tests/integration/api
python -m pytest tests/integration/data
python -m pytest tests/smoke
```

## Data/config validation

```bash
country-compare validate-config
country-compare validate-data
```

## Data correctness layer

The data correctness tests validate values and provenance, not just schema shape. Keep fixtures current when data sources, units, or expected values change.

| Test area | Purpose | Typical fixture |
| --- | --- | --- |
| Golden values | Compare critical rows to trusted references. | `tests/fixtures/data/golden_values.yaml` |
| Source alignment | Ensure metrics point to expected source families. | `tests/fixtures/data/expected_metric_sources.yaml` |
| Unit/scale correctness | Catch percent/fraction/index/currency scale mistakes. | `tests/fixtures/data/metric_unit_rules.yaml` |
| Plausibility ranges | Catch impossible or suspicious values. | `tests/fixtures/data/metric_plausibility_rules.yaml` |
| Missingness/staleness | Catch unexpectedly sparse or stale metrics. | Data fixture rules under `tests/fixtures/data/` |

Run:

```bash
python -m pytest tests/integration/data
```

## API checks

```bash
python -m pytest tests/integration/api
python -m pytest tests/unit/clients
```

Manual smoke with a running backend:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/v1/metadata/dataset
curl http://localhost:8000/api/v1/metadata/prediction-methods
```

## UI checks

```bash
python -m pytest tests/unit/ui
```

Manual UI checks should cover both local and HTTP-backed modes.

## LLM service checks

```bash
cd services/llm_forecast_service
python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src
cd ../..
```

Also run main-app tests that cover `llm_forecast` availability gating.

## Container checks

```bash
docker compose build
docker compose --profile llm build llm-forecast
```

With a running backend:

```bash
python scripts/smoke_api_container.py --base-url http://localhost:8000
```

## Release candidate checklist

- [ ] `country-compare validate-config` passes.
- [ ] `country-compare validate-data` passes.
- [ ] `python -m pytest` passes.
- [ ] lint, format, and type checks pass.
- [ ] LLM service checks pass if affected.
- [ ] Docker builds pass.
- [ ] `/health`, `/ready`, and representative API calls pass.
- [ ] UI local and HTTP modes render representative workflows.
- [ ] Optional `/ready/llm` behavior matches intended deployment state.
- [ ] Docs and README files reflect changed commands, env vars, endpoints, and limitations.
