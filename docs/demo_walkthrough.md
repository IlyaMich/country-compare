# Golden Demo Walkthrough

This walkthrough verifies the Country Compare product flow without remote downloads or external data dependencies.

## Files

- `data/examples/golden_demo_metrics.csv`
- `config/demo_metrics.yaml`
- `config/demo_scoring_profiles.yaml`
- `scripts/demo_product_flow.py`

## What the demo proves

The demo runs this deterministic flow:

```text
load demo data
→ validate canonical data
→ run single-metric comparison
→ run multi-metric comparison
→ run weighted score
→ run forecast
→ run predicted comparison
→ export result CSV files