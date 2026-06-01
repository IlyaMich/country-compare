# Demo walkthrough

Use this flow to demonstrate the current project without modifying data or config.

## 1. Start the app locally

In-process UI mode:

```bash
country-compare ui
```

HTTP-backed mode:

```bash
python -m uvicorn country_compare.api.main:app --host 0.0.0.0 --port 8000
COUNTRY_COMPARE_API_URL=http://localhost:8000 python -m streamlit run src/country_compare/ui/app.py
```

Container mode:

```bash
docker compose up --build
```

## 2. Show readiness and metadata

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/v1/metadata/dataset
curl http://localhost:8000/api/v1/metadata/prediction-methods
```

Explain that readiness validates dataset/config traffic readiness, while health is process liveness only.

## 3. Single-metric comparison

In the UI, select three or more countries and one metric such as GDP per capita or life expectancy. Run a single-metric comparison and show:

- ranked table;
- selected year strategy;
- warnings/diagnostics;
- export controls.

## 4. Multi-metric comparison

Select multiple metrics and show how the result changes. Explain that `higher_is_better` affects ranking and normalization.

## 5. Weighted profile scoring

Select a scoring profile such as an economic or general profile. Show profile metadata and resulting ranked countries.

## 6. Prediction

Run a baseline forecast:

- select countries;
- select one metric;
- choose `linear_trend` with fallback `last_observed`;
- set a short horizon;
- show actuals, forecasts, diagnostics, and warnings.

## 7. Backtesting

Run a backtest for a country/metric series. Explain holdout years and that prediction quality depends on history length, staleness, and structural breaks.

## 8. Predicted comparisons

Show a predicted single-metric, profile, or multi-metric comparison using a future forecast year/horizon.

## 9. Optional LLM forecast

Only show this when the LLM profile is running and `/ready/llm` is ready:

```bash
docker compose --profile llm -f docker-compose.yml -f docker-compose.llm-local.yml up --build
curl http://localhost:8000/ready/llm
```

Explain that `llm_forecast` is an experimental bounded adjustment over deterministic forecasts, not an authoritative prediction.

## 10. Exports

Show CSV table export, diagnostics JSON, and Markdown summaries from result panels.

## 11. Close the loop with checks

```bash
country-compare validate-config
country-compare validate-data
python -m pytest tests/smoke
```
