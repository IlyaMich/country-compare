# Canonical dataset contract

The processed dataset is canonical long-format data with one row per:

```text
country_code + metric_id + year
```

## Required columns

| Column | Meaning |
| --- | --- |
| `country_code` | Stable country code used by selectors and APIs. |
| `country_name` | Human-readable country name. |
| `metric_id` | Stable metric identifier used by config, scoring, comparison, and prediction. |
| `metric_name` | Human-readable metric name. |
| `value` | Numeric metric value. |
| `year` | Observation year. |
| `unit` | Display/scale unit. |
| `source_name` | Source family or provider name. |
| `source_url` | Source URL or documentation URL. |
| `higher_is_better` | Boolean direction for ranking/scoring. |
| `category` | Metric category such as economy, health, governance, or social. |

## Optional columns

```text
dataset_version
region
income_group
notes
```

Optional columns can improve display, filtering, diagnostics, and provenance. They should not break consumers if absent.

## Rules

- Preserve long-format storage. Do not add feature-specific wide tables as primary storage.
- Keep `metric_id` stable once used by config, tests, UI, or API consumers.
- Fill `source_name`, `source_url`, `unit`, `category`, and `higher_is_better` for every metric.
- Respect `higher_is_better` in ranking, scoring, normalization, and comparisons.
- Treat missing values explicitly; do not silently coerce missing values into zeros.
- Use derived/wide tables only transiently inside services or presentation helpers.

## Validation commands

```bash
country-compare validate-config
country-compare validate-data
```

## Data correctness tests

The current test plan includes structural and data-correctness checks. Data-correctness fixtures live under `tests/fixtures/data/` and cover:

- golden values against trusted references;
- source family alignment by metric;
- units and scale expectations;
- plausibility ranges;
- missingness/staleness expectations;
- canonical schema and duplicate key checks.

Run focused checks:

```bash
python -m pytest tests/integration/data
```

## Adding a metric

1. Add metric metadata/config.
2. Transform source data into the canonical long-format shape.
3. Set `higher_is_better`, `unit`, `category`, and source metadata correctly.
4. Add or update fixture rules for source alignment, unit/scale, plausibility, and golden values where appropriate.
5. Run config/data validation and integration data tests.
6. Confirm UI selectors and `/api/v1/metadata/metrics` expose the metric.

## Adding a source manifest

1. Add a manifest under `config/source_manifests/`.
2. Keep acquisition and processing code in pipeline modules.
3. Preserve canonical output columns.
4. Publish the processed output only after validation passes.
5. Update docs or metadata catalogs if source coverage changed.
