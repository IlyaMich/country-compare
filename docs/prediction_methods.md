# Prediction Methods

Country Compare supports baseline, statistical, optional machine-learning, and experimental AI-assisted forecasting methods.

Forecasts are projections from historical metric values. They are not guarantees and do not model all possible real-world drivers, such as policy changes, economic shocks, methodology revisions, wars, pandemics, reporting delays, or future source-data corrections.

Use prediction outputs as exploratory decision-support signals, not as authoritative future facts.

---

## Method catalog

| Method ID | Label | Type | Dependency | Default availability |
|---|---|---|---|---|
| `last_observed` | Last observed value | Baseline | Base install | Available |
| `linear_trend` | Linear trend | Statistical | Base install | Available |
| `moving_average` | Moving average | Baseline/statistical | Base install | Available |
| `holt_linear` | Holt linear trend | Statistical | Base install | Available |
| `elasticnet_trend` | ElasticNet trend | Machine learning | `country-compare[ml]` | Available only when ML dependencies are installed |
| `llm_forecast` | LLM forecast — experimental | AI-assisted | Provider/client configuration | Disabled by default |

---

## General forecast behavior

Prediction methods use the existing processed Country Compare dataset.

The normal flow is:

```text
processed historical dataset
  -> selected country/metric series
  -> selected prediction method
  -> forecast points
  -> diagnostics, warnings, and result tables
```

Prediction methods are expected to return:

```text
- forecast year
- forecast value
- horizon
- method used
- diagnostics
- warnings when applicable
```

Where supported by the UI/API flow, methods can also participate in:

```text
- single-metric forecasts
- multi-country forecasts
- predicted comparisons
- predicted profile comparisons
- backtesting
```

Backtesting should be interpreted as a historical holdout evaluation. Good backtest results do not guarantee future accuracy.

---

## `last_observed`

`last_observed` repeats the latest observed value for every future forecast year.

### Type

Baseline.

### Dependencies

Base install only.

### Typical use

Use this method as a simple baseline or fallback when trend-based methods cannot run.

### Strengths

- Very simple and stable.
- Works with minimal history.
- Useful as a conservative fallback.

### Limitations

- Does not model growth, decline, cycles, or trend changes.
- Can understate or overstate future values when the metric has a clear trend.
- Should mainly be used as a baseline comparison method.

---

## `linear_trend`

`linear_trend` fits a simple linear trend over the historical series and extrapolates future values.

### Type

Statistical.

### Dependencies

Base install only.

### Typical use

Use this method for metrics with a reasonably stable long-term upward or downward trend.

### Strengths

- Easy to understand.
- Captures a simple direction and slope.
- Useful as a transparent statistical baseline.

### Limitations

- Assumes the historical trend continues linearly.
- Can overstate temporary changes.
- Can produce unrealistic forecasts for bounded or highly volatile metrics.
- Sensitive to unusual historical periods.

---

## `moving_average`

`moving_average` forecasts from recent observed values.

### Type

Baseline/statistical.

### Dependencies

Base install only.

### Typical use

Use this method for short-horizon forecasts where recent values are more important than long-term trend.

### Strengths

- Smooths short-term volatility.
- Less sensitive to older historical values.
- Simple and explainable.

### Limitations

- Does not explicitly model trend.
- Can lag behind real changes.
- May be weak for strongly trending series.

---

## `holt_linear`

`holt_linear` applies additive Holt linear smoothing with an optional damped trend.

### Type

Statistical.

### Dependencies

Base install only.

### Typical use

Use this method when you want a trend-aware forecast that is more adaptive than a simple global linear trend.

### Recommended data shape

This method works best with:

```text
- numeric annual observations
- at least several historical years
- reasonably consistent time-series history
```

### Expected behavior

The method estimates:

```text
- level
- trend
```

and then projects future values from the final smoothed level and trend.

When dampening is enabled, the projected trend contribution gradually reduces over longer horizons.

### Diagnostics

Diagnostics may include:

```text
method
alpha
beta
damped
phi
training_observation_count
training_year_min
training_year_max
final_level
final_trend
warnings
```

### Strengths

- Captures recent trend behavior.
- More adaptive than a single global linear regression.
- Lightweight and deterministic.
- Does not require additional dependencies.

### Limitations

- Still assumes the smoothed historical trend is informative for the future.
- Does not model external drivers.
- Can be affected by sparse or irregular histories.
- Long-horizon forecasts should be interpreted cautiously.

---

## `elasticnet_trend`

`elasticnet_trend` fits a lightweight regularized trend model using year-derived features.

The initial implementation uses deterministic features such as:

```text
year_offset
year_offset_squared
```

No pre-trained model artifact is required. The model is fit on demand for each country and metric series.

### Type

Machine learning / regularized regression.

### Dependencies

Requires the optional ML dependency extra.

For local development with tests:

```bash
python -m pip install -e ".[dev,ml]"
```

For a deployed backend that should expose this method:

```bash
python -m pip install ".[api,ml]"
```

If the ML dependency is not installed, the app should still start normally and `elasticnet_trend` should not be listed as an available method.

### Typical use

Use this method when you want a lightweight ML trend model that can capture simple non-linear trend curvature while using regularization to reduce overfitting risk.

### Expected behavior

The method:

```text
1. Reads the selected historical country/metric series.
2. Builds deterministic year-based features.
3. Fits an ElasticNet model.
4. Predicts feature rows for future years.
5. Returns forecast points and diagnostics.
```

### Diagnostics

Diagnostics may include:

```text
method
dependency_available
features
alpha
l1_ratio
max_iter
training_observation_count
training_year_min
training_year_max
coefficients
intercept
warnings
```

### Strengths

- More flexible than a strict linear trend.
- Uses regularization to reduce overfitting risk.
- Lightweight enough to run in-process.
- Does not require a persisted model artifact.

### Limitations

- Requires enough observations to fit safely.
- Still only models year-based trend features.
- Does not include macroeconomic, policy, or other external explanatory variables.
- May not outperform simpler methods on short or noisy histories.
- Can extrapolate poorly when historical curvature is not stable.

### Deployment notes

For small containers, consider setting numerical-library thread limits in the backend runtime environment:

```text
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
```

These are runtime environment variables for the backend service. They are not model settings.

---

## `llm_forecast`

`llm_forecast` is an experimental AI-assisted forecast method.

It is disabled by default and should remain unavailable unless explicitly enabled and configured.

### Type

AI-assisted / experimental.

### Default availability

Disabled by default.

### Intended design

The method should not allow an LLM to freely invent unconstrained forecast numbers.

The intended flow is:

```text
historical series
  -> deterministic baseline forecast
  -> LLM receives compact history + baseline + context
  -> LLM returns structured output
  -> code validates output strictly
  -> validated LLM-adjusted forecast is returned
  -> fallback is used if validation/provider call fails
```

### Important trust boundary

The LLM response is not trusted directly.

The application must validate:

```text
- response parses as structured data
- forecast point count matches requested horizon
- forecast years match expected future years
- values are numeric
- values are finite
- values do not exceed configured adjustment bounds
```

If validation fails, the method should return a deterministic fallback forecast and visible warnings.

### Default environment settings

```text
COUNTRY_COMPARE_ENABLE_LLM_FORECAST=false
COUNTRY_COMPARE_LLM_PROVIDER=
COUNTRY_COMPARE_LLM_MODEL=
COUNTRY_COMPARE_LLM_TIMEOUT_SECONDS=20
COUNTRY_COMPARE_LLM_MAX_RETRIES=1
COUNTRY_COMPARE_LLM_BASELINE_METHOD=holt_linear
COUNTRY_COMPARE_LLM_MAX_HISTORY_POINTS=40
COUNTRY_COMPARE_LLM_MAX_ADJUSTMENT_PCT=20
```

### Provider/client configuration

Provider credentials must remain server-side.

Do not expose provider API keys to:

```text
- Streamlit UI clients
- browser clients
- frontend configuration
- API response payloads
- logs
```

A real provider adapter should be added only when the backend is ready to manage:

```text
- provider credentials
- timeouts
- retries
- rate limits
- provider errors
- response validation
- safe fallback behavior
```

### Current implementation status

The current implementation may include the provider-neutral interface and mocked tests without a real provider adapter.

In that state:

```text
- normal local usage should not expose llm_forecast
- deployed usage should not expose llm_forecast
- tests can use fake/stub clients
- no real LLM provider should be called in tests
```

### Diagnostics

Diagnostics may include:

```text
method
experimental
enabled
provider
model
prompt_version
baseline_method
timeout_seconds
max_retries
max_history_points
max_adjustment_pct
llm_called
validation_status
fallback_used
fallback_method
failure_reason
rationale
assumptions
risk_warnings
raw_provider_metadata
```

### User-facing warning

LLM forecasts should be shown with a visible warning such as:

```text
This forecast is AI-assisted and should be treated as an exploratory scenario, not a guarantee. Review the baseline forecast, assumptions, and diagnostics before relying on it.
```

### Strengths

- Can provide structured assumptions and scenario-style explanation.
- Can adjust a deterministic baseline when a validated provider adapter is configured.
- Designed with fallback and validation guardrails.

### Limitations

- Experimental.
- Disabled by default.
- Requires provider/client configuration before real use.
- May be slower or more expensive than deterministic methods.
- Provider output can be invalid or unavailable.
- Should not be used as a guaranteed forecast.
- Should not be enabled without monitoring and fallback validation.

---

## Availability behavior

Prediction methods should be listed according to runtime availability.

Expected behavior:

```text
Base install:
- last_observed
- linear_trend
- moving_average
- holt_linear

Install with ML extra:
- last_observed
- linear_trend
- moving_average
- holt_linear
- elasticnet_trend

LLM disabled/default:
- llm_forecast hidden or unavailable

LLM enabled with configured client/provider:
- llm_forecast may be listed as experimental
```

If a method is unavailable, the app should fail cleanly or hide the method rather than crashing at startup.

---

## Local development

Base development install:

```bash
python -m pip install -e ".[dev]"
```

Development install with ML support:

```bash
python -m pip install -e ".[dev,ml]"
```

Run tests:

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
```

Run focused prediction tests:

```bash
python -m pytest tests/unit/prediction
```

Run the Streamlit UI locally:

```bash
country-compare ui
```

or:

```bash
python -m streamlit run src/country_compare/ui/app.py
```

---

## Backend/API deployment

To expose `elasticnet_trend` in the deployed backend, install the backend with the ML extra:

```bash
python -m pip install ".[api,ml]"
```

If using Docker, the backend image should install the equivalent package extras.

Example:

```dockerfile
RUN python -m pip install ".[api,ml]"
```

If the backend is installed without `ml`, the service should still work, but `elasticnet_trend` should not be available.

No extra data artifact is required for `holt_linear` or `elasticnet_trend`.

No trained model artifact is required for `elasticnet_trend`.

The deployed backend needs:

```text
- processed dataset
- config files
- updated source code
- ML dependencies if elasticnet_trend should be available
- provider/client configuration only if llm_forecast is intentionally enabled later
```

---

## API usage

The existing prediction endpoints should accept available methods through the normal `method` field.

Example request body:

```json
{
  "country_codes": ["ISR"],
  "metric_id": "gdp_per_capita",
  "horizon_years": 3,
  "method": "holt_linear",
  "fallback_method": "last_observed",
  "history_start_year": null,
  "history_end_year": null,
  "scenario_id": "baseline"
}
```

For `elasticnet_trend`:

```json
{
  "country_codes": ["ISR"],
  "metric_id": "gdp_per_capita",
  "horizon_years": 3,
  "method": "elasticnet_trend",
  "fallback_method": "last_observed",
  "history_start_year": null,
  "history_end_year": null,
  "scenario_id": "baseline"
}
```

For `llm_forecast`, only use this when the backend has been explicitly enabled and configured:

```json
{
  "country_codes": ["ISR"],
  "metric_id": "gdp_per_capita",
  "horizon_years": 3,
  "method": "llm_forecast",
  "fallback_method": "last_observed",
  "history_start_year": null,
  "history_end_year": null,
  "scenario_id": "baseline"
}
```

No separate public LLM endpoint is required.

---

## Manual QA checklist

After adding or changing prediction methods, verify:

```text
- UI starts in local mode
- UI starts in HTTP-backed mode
- backend /health returns 200
- backend /ready returns ready when dataset/config are valid
- holt_linear appears in method selectors
- holt_linear can produce a forecast
- holt_linear can run through backtesting if supported by the workflow
- elasticnet_trend appears when ML dependencies are installed
- elasticnet_trend does not appear when ML dependencies are missing
- elasticnet_trend can produce a forecast with sufficient history
- elasticnet_trend falls back or fails cleanly with insufficient history
- llm_forecast does not appear by default
- llm_forecast is clearly marked experimental if enabled in a test/dev environment
- LLM fallback warnings are visible when fallback is used
- prediction diagnostics remain visible
- existing methods still work
```

---

## Final validation commands

Run:

```bash
python -m pytest
python -m ruff check src/country_compare tests scripts
python -m black --check src/country_compare tests scripts
python -m mypy src/country_compare
```

With ML dependencies installed:

```bash
python -m pip install -e ".[dev,ml]"
python -m pytest tests/unit/prediction
```

For Docker validation:

```bash
docker compose build
docker compose up --build
```

Then manually check:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8501
```