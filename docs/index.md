# Country Compare Documentation

Country Compare is a Python application for comparing countries across metrics, weighted scoring profiles, and baseline prediction workflows.

This documentation set describes the `v0.1 beta` state of the project.

## Current beta capabilities

- Core country comparison workflows.
- Weighted/profile scoring workflows.
- Prediction and backtesting workflows.
- Read-only FastAPI backend.
- Streamlit UI with local and HTTP-backed modes.
- Docker Compose split between backend and UI containers.
- `/src` package layout.
- Streamlit-native visualizations in both local and HTTP-backed/container modes where returned data supports them.

## Supported run modes

| Mode | Description |
|---|---|
| Local UI mode | Streamlit runs in-process and calls local services directly. |
| HTTP-backed UI mode | Streamlit calls the FastAPI backend through the HTTP client. |
| Docker Compose mode | Backend and UI run as separate containers. |
| CLI mode | Validation and app commands run through `country-compare`. |

## Documentation map

- [Getting started](getting_started.md)
- [Architecture](architecture.md)
- [API reference](api.md)
- [Configuration](configuration.md)
- [Data contract](data_contract.md)
- [User guide](user_guide.md)
- [Prediction behavior](prediction.md)
- [Containerization](containerization.md)
- [Development guide](development.md)
- [Testing guide](testing.md)
- [Manual QA checklist](manual_qa.md)
- [Troubleshooting](troubleshooting.md)
- [Release notes](release_notes_v0_1_beta.md)

## Important package rule

The package lives under:

```text
src/country_compare
```

But Python imports must remain:

```python
import country_compare
```

Never import:

```python
import src.country_compare
```
