# Contributing to Country Compare

Thank you for your interest in contributing to Country Compare.

Contributions are welcome, including bug fixes, tests, documentation improvements, data/configuration improvements, and new functionality.

For larger changes, consider opening an issue before starting implementation so the proposed approach can be discussed first.

## Development setup

Country Compare requires Python 3.11 or newer.

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install the project and development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the Streamlit application locally:

```bash
country-compare ui
```

Run the FastAPI backend locally:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
```

The normal Docker Compose stack can also be started with:

```bash
docker compose up --build
```

## Project architecture

Country Compare separates framework-specific code from application and domain logic.

When making changes, preserve these boundaries:

* `country_compare.ui` owns Streamlit presentation behavior.
* `country_compare.clients` provides the interface used by the UI for both local and HTTP-backed execution.
* `country_compare.api` owns HTTP transport, schemas, request validation, security, serialization, and error mapping.
* `country_compare.services` orchestrates application workflows.
* Domain packages such as `comparison`, `prediction`, `scoring`, `data`, `config`, and `pipelines` contain framework-independent application logic.
* `services/llm_forecast_service` is a separate private service for bounded LLM-assisted forecast adjustments.

Business logic should not be implemented directly in FastAPI routes or Streamlit views.

The public backend API is intentionally read-only. Changes that introduce ingestion, configuration editing, dataset refresh execution, or other write operations should not be added to the existing public API without an explicit architectural decision.

UI-facing functionality should continue to work through both the local and HTTP clients where applicable.

API responses must remain JSON-safe.

## Python imports

Import the package using:

```python
import country_compare
```

Do not import application modules through `src.country_compare`.

## Testing and quality checks

Before submitting a pull request, run the main project checks:

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
```

The Makefile also provides shortcuts:

```bash
make check
make check-all
```

If your change affects Docker or runtime packaging, also verify the relevant container builds:

```bash
docker compose build
docker compose --profile llm build llm-forecast
```

## LLM forecast service changes

If your change affects `services/llm_forecast_service`, run its checks separately:

```bash
cd services/llm_forecast_service

python -m pytest
python -m ruff check src tests
python -m black --check src tests
python -m mypy src

cd ../..
```

Or from the repository root:

```bash
make llm-check
```

The LLM forecast service must remain private and token-protected.

LLM-assisted forecasting should remain a bounded adjustment to deterministic baseline forecasts rather than replacing the deterministic forecasting pipeline.

Do not commit provider API keys, service tokens, credentials, or other secrets.

## Data and configuration changes

Changes to canonical data, metric configuration, scoring profiles, or source manifests should preserve the existing data contracts.

Run:

```bash
country-compare validate-config
country-compare validate-data
```

when the corresponding configuration or data is changed.

Canonical metric data should continue to use one row per country, metric, and year and preserve the metadata expected by the application.

## Tests

New behavior should normally include tests at the lowest appropriate layer.

Depending on the change, this may include:

* domain or service unit tests;
* API integration tests;
* local/HTTP client tests;
* UI tests;
* data correctness tests;
* smoke tests.

Bug fixes should include a regression test when practical.

## Documentation

Update documentation when a change affects:

* public behavior;
* API contracts;
* configuration or environment variables;
* installation or deployment;
* architecture;
* prediction behavior or limitations;
* the LLM forecast service.

The documentation entry point is:

```text
docs/index.md
```

## Pull requests

Keep pull requests focused on one logical change whenever practical.

A pull request should explain:

* what changed;
* why the change is needed;
* any important design decisions;
* how the change was tested;
* whether documentation, configuration, API behavior, or deployment behavior changed.

Make sure CI passes before considering the change ready to merge.

## Reporting bugs and requesting features

Normal bugs, feature requests, and documentation issues may be submitted through GitHub Issues.

Before opening a new issue, check whether an existing issue already covers the same topic.

Security vulnerabilities should **not** be reported through a public issue. See [SECURITY.md](SECURITY.md) instead.

## Security and secrets

Never commit:

* API keys;
* authentication tokens;
* passwords;
* private service credentials;
* `.env` files containing real secrets;
* production credentials or private deployment information.

Use environment variables and repository/deployment secret stores as appropriate.

If a contribution accidentally exposes a secret, revoke or rotate the affected credential immediately rather than relying only on removing it from Git history.

## License

Country Compare is licensed under the Apache License 2.0.

By submitting a contribution for inclusion in this project, you agree that your contribution may be distributed under the terms of the project's [Apache License 2.0](LICENSE).
