# Dataset replacement and refresh

This project treats the processed dataset as an artifact produced by pipelines, not as something edited by the API or UI.

## Replacement workflow

1. Prepare or acquire raw/source data.
2. Update or add source manifests under `config/source_manifests/`.
3. Run the processing/update command.
4. Validate the processed dataset.
5. Run data correctness and API/UI smoke tests.
6. Commit or publish the processed artifact according to the repository release process.

Example update command:

```bash
country-compare update-data --manifest config/source_manifests/world_bank_real_data.yaml
```

Validation:

```bash
country-compare validate-config
country-compare validate-data
python -m pytest tests/integration/data
```

## Canonical shape

The processed dataset must remain long-format with one row per `country_code + metric_id + year` and the required columns listed in `data_contract.md`.

## Source alignment

Each metric should point to the expected source family and use the expected unit/scale. Update these fixtures when a deliberate source or unit change is made:

```text
tests/fixtures/data/expected_metric_sources.yaml
tests/fixtures/data/metric_unit_rules.yaml
tests/fixtures/data/metric_plausibility_rules.yaml
tests/fixtures/data/golden_values.yaml
```

## API/UI impact checklist

After replacing data:

- `/api/v1/metadata/dataset` shows the expected row, country, metric, and year counts.
- `/api/v1/metadata/countries` contains expected country codes/names.
- `/api/v1/metadata/metrics` contains expected metrics, units, and categories.
- `/ready` returns ready.
- Representative comparison and scoring requests work.
- Prediction/backtest workflows produce diagnostics rather than hard failures for sparse series.
- UI selectors still load and result panels render.

## What not to do

Do not add an API endpoint that refreshes the dataset, runs ingestion, or edits config in the current read-only backend. Run refresh/publish workflows outside the API process.
