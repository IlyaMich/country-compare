# Configuration

Country Compare configuration is split between project config files, runtime environment variables, and Python defaults.

## Project config files

Typical repository-level config files:

```text
config/metrics.yaml
config/scoring_profiles.yaml
```

### `config/metrics.yaml`

Defines metric metadata used by comparison, scoring, prediction, and UI selectors.

Common concepts include:

- metric ID
- display name
- category
- unit
- whether higher values are better
- source information

### `config/scoring_profiles.yaml`

Defines weighted scoring profiles.

Common concepts include:

- profile name
- description
- included metric IDs
- weights
- year strategy
- missing-data behavior, if configured

## Runtime environment variables

### `COUNTRY_COMPARE_API_URL`

Controls Streamlit client mode.

Unset:

```text
Streamlit uses local in-process services.
```

Set:

```text
Streamlit uses the HTTP client and calls the configured FastAPI backend.
```

Example:

```bash
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

### `COUNTRY_COMPARE_API_CORS_ORIGINS`

API-only setting for CORS origins.

### `COUNTRY_COMPARE_API_MAX_RECORDS`

API-only setting for maximum serialized records in table payloads.

### `COUNTRY_COMPARE_API_ENABLE_DOCS`

API-only setting for enabling or disabling generated FastAPI docs.

## Python defaults

Application defaults live under:

```text
src/country_compare/settings/
```

Important modules:

```text
src/country_compare/settings/defaults.py
src/country_compare/settings/app_settings.py
```

Defaults can include values such as:

- prediction method defaults
- fallback method defaults
- maximum forecast horizon
- maximum backtest holdout years
- dataset/store-related defaults

## UI labels and text

Stable UI labels and reusable user-facing text should live in UI text/label modules where appropriate, such as:

```text
src/country_compare/ui/text.py
src/country_compare/ui/navigation.py
```

One-off explanatory copy can remain local to the relevant UI component.

## Config validation

Before running beta workflows, validate configuration and data:

```bash
country-compare validate-config
country-compare validate-data
```

The backend readiness endpoint also validates that the service is ready to serve traffic:

```text
http://localhost:8000/ready
```
