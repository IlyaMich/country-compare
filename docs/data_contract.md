# Data Contract

Country Compare workflows depend on a canonical processed metrics dataset.

The application is designed around a long-format table where each row represents one country, one metric, and one year.

## Recommended canonical columns

| Column | Description |
|---|---|
| `country_code` | Stable country identifier, such as ISO-style code. |
| `country_name` | Human-readable country name. |
| `metric_id` | Stable metric identifier used by config and services. |
| `metric_name` | Human-readable metric name. |
| `year` | Observation year. |
| `value` | Numeric metric value. |
| `unit` | Unit for display and interpretation. |
| `source_name` | Human-readable data source name. |
| `source_url` | Source URL, if available. |
| `higher_is_better` | Whether larger values are better for ranking/scoring. |
| `category` | Metric category used by selectors and display. |

## Optional columns

Optional metadata may include:

| Column | Description |
|---|---|
| `dataset_version` | Processed dataset version. |
| `region` | Region or geographic grouping. |
| `income_group` | Income classification, if available. |
| `notes` | Additional source or processing notes. |

## Logical primary key

The logical primary key is usually:

```text
country_code + metric_id + year
```

Duplicate rows for the same key should be avoided unless a workflow explicitly supports multiple source observations.

## Value expectations

- `value` should be numeric for metric observations.
- Missing values should be represented consistently and validated before publication.
- `year` should be an integer-like year value.
- `metric_id` values should align with `config/metrics.yaml`.

## Comparison assumptions

Comparison workflows expect enough data to identify a country, metric, year, and numeric value.

Common table concepts:

```text
country_code
country_name
metric_id
metric_name
year
value
rank
score
```

## Prediction assumptions

Prediction workflows need historical values for a selected country and metric.

Sparse series may trigger warnings, fallback methods, or failed-series diagnostics. Prediction outputs should preserve enough data for:

- forecast tables
- actual-vs-forecast visualization
- diagnostics
- backtest error summaries
- actual-vs-predicted backtest tables

## API serialization

The API does not return raw pandas objects. DataFrames are serialized into JSON-safe table payloads with:

```text
row_count
column_count
columns
records
records_truncated
```

The HTTP-backed UI reconstructs DataFrames from these payloads where needed.
