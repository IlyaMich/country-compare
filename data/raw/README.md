# Raw World Bank source data

This directory contains the raw CSV source files used to generate the processed
Country Compare dataset.

The raw files are the source of truth for the generated dataset artifacts used by
the application and API.

## Source

The CSV files in this directory were downloaded from World Bank Open Data:

```text
https://data.worldbank.org/
```

Directory structure:

```text
data/raw/<metric_name>/<metric_name>.csv
```

Each metric directory contains the raw CSV source file for one metric.

## License and attribution

These raw CSV files are sourced from World Bank Open Data. At the time these
files were added, the reviewed World Bank datasets indicated a Creative Commons
Attribution 4.0 International license, unless otherwise indicated by the
specific source dataset.

When adding or replacing raw files, verify the license shown by the source
dataset page.

Attribution:

```text
Source: World Bank Open Data, https://data.worldbank.org/.
Licensed under Creative Commons Attribution 4.0 International unless otherwise
indicated by the source dataset.
```

## Sensitive data policy

The files in this directory should contain only public, aggregate source data
downloaded from World Bank Open Data.

Do not add private files, manually collected personal data, credentials,
proprietary data, or temporary local exports to this directory.

## Generated artifacts

The following processed artifacts are generated from the raw CSV files and are
intentionally not committed to Git:

```text
data/processed/metrics.parquet
data/processed/metrics_manifest.json
data/processed/catalog.json
```

Regenerate them with:

```bash
python scripts/update_parquet_data_wb.py --skip-audit
```

The generated artifact set should always be treated as a unit:

```text
metrics.parquet
metrics_manifest.json
catalog.json
```

Do not replace only one generated file in a deployed environment unless you are
intentionally recovering from a failed or partial deployment.

## CI behavior

CI regenerates the processed dataset artifacts from these committed raw CSV
files before running validation, tests, Docker builds, and backend smoke checks.

This verifies that the project can be rebuilt from source inputs rather than
depending on committed generated parquet or metadata files.

## Repository policy

Commit:

```text
data/raw/**/*.csv
data/raw/README.md
data/processed/.gitkeep
```

Do not commit:

```text
data/processed/metrics.parquet
data/processed/metrics_manifest.json
data/processed/catalog.json
```