# Containerization

Country Compare can run as a single Docker container. In this mode, the Streamlit UI and Python service/backend layer run in the same process.

## Build

```bash
docker build -t country-compare:local .

```

## Run
```bash
docker run --rm \
  -p 8501:8501 \
  -e COUNTRY_COMPARE_METRICS_CONFIG=/app/config/metrics.yaml \
  -e COUNTRY_COMPARE_SCORING_CONFIG=/app/config/scoring_profiles.yaml \
  -e COUNTRY_COMPARE_STORE_BACKEND=parquet \
  -e COUNTRY_COMPARE_STORE_PATH=/app/data/processed/metrics.parquet \
  -v "$(pwd)/config:/app/config:ro" \
  -v "$(pwd)/data:/app/data" \
  country-compare:local

```
```PowerShell
docker run --rm ^
  -p 8501:8501 ^
  -e COUNTRY_COMPARE_METRICS_CONFIG=/app/config/metrics.yaml ^
  -e COUNTRY_COMPARE_SCORING_CONFIG=/app/config/scoring_profiles.yaml ^
  -e COUNTRY_COMPARE_STORE_BACKEND=parquet ^
  -e COUNTRY_COMPARE_STORE_PATH=/app/data/processed/metrics.parquet ^
  -e COUNTRY_COMPARE_DEBUG=false ^
  -v "%cd%\config:/app/config:ro" ^
  -v "%cd%\data:/app/data" ^
  country-compare:local

```