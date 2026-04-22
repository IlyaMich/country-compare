from __future__ import annotations

import pandas as pd

from country_compare.data.validation import (
    coerce_to_canonical_dtypes,
    normalize_canonical_columns,
    validate_and_parse_dataframe,
)


COUNTRIES: dict[str, dict[str, str]] = {
    "ISR": {
        "country_name": "Israel",
        "region": "Middle East",
        "income_group": "High income",
    },
    "DEU": {
        "country_name": "Germany",
        "region": "Europe",
        "income_group": "High income",
    },
    "SGP": {
        "country_name": "Singapore",
        "region": "Asia",
        "income_group": "High income",
    },
    "CAN": {
        "country_name": "Canada",
        "region": "North America",
        "income_group": "High income",
    },
    "JPN": {
        "country_name": "Japan",
        "region": "Asia",
        "income_group": "High income",
    },
}


METRICS: dict[str, dict[str, object]] = {
    "gdp_per_capita": {
        "metric_name": "GDP per capita",
        "unit": "USD",
        "source_name": "Example Source",
        "source_url": "https://example.org/gdp",
        "higher_is_better": True,
        "category": "economy",
        "yearly_values": {
            2022: {"ISR": 54000.0, "DEU": 65000.0, "SGP": 140000.0, "CAN": 59000.0, "JPN": 42000.0},
            2023: {"ISR": 56000.0, "DEU": 67000.0, "SGP": 145000.0, "CAN": 61000.0, "JPN": 43500.0},
        },
        "notes_by_year": {
            2023: "Example updated year.",
        },
    },
    "rule_of_law": {
        "metric_name": "Rule of Law",
        "unit": "index",
        "source_name": "Example Source",
        "source_url": "https://example.org/rule-of-law",
        "higher_is_better": True,
        "category": "governance",
        "yearly_values": {
            2022: {"ISR": 0.67, "DEU": 0.84, "SGP": 0.83, "CAN": 0.91, "JPN": 0.79},
            2023: {"ISR": 0.66, "DEU": 0.85, "SGP": 0.84, "CAN": 0.92, "JPN": 0.80},
        },
    },
    "democracy_index": {
        "metric_name": "Democracy Index",
        "unit": "score_0_10",
        "source_name": "Example Source",
        "source_url": "https://example.org/democracy-index",
        "higher_is_better": True,
        "category": "governance",
        "yearly_values": {
            2022: {"ISR": 7.8, "DEU": 8.8, "SGP": 6.2, "CAN": 9.0, "JPN": 8.2},
            2023: {"ISR": 7.6, "DEU": 8.8, "SGP": 6.3, "CAN": 9.0, "JPN": 8.1},
        },
    },
    "inflation": {
        "metric_name": "Inflation",
        "unit": "percent",
        "source_name": "Example Source",
        "source_url": "https://example.org/inflation",
        "higher_is_better": False,
        "category": "economy",
        "yearly_values": {
            2022: {"ISR": 4.4, "DEU": 6.9, "SGP": 6.1, "CAN": 6.8, "JPN": 2.5},
            2023: {"ISR": 3.1, "DEU": 5.9, "SGP": 4.8, "CAN": 3.9, "JPN": 3.2},
        },
        "notes_by_year": {
            2022: "Lower is better for this metric.",
            2023: "Lower is better for this metric.",
        },
    },
    "life_expectancy": {
        "metric_name": "Life Expectancy",
        "unit": "years",
        "source_name": "Example Source",
        "source_url": "https://example.org/life-expectancy",
        "higher_is_better": True,
        "category": "health",
        "yearly_values": {
            2022: {"ISR": 82.7, "DEU": 80.8, "SGP": 83.5, "CAN": 82.3, "JPN": 84.4},
            2023: {"ISR": 82.9, "DEU": 81.0, "SGP": 83.8, "CAN": 82.5, "JPN": 84.6},
        },
    },
}


DATASET_VERSION = "v0.2.0"


def _build_metric_rows(
    *,
    metric_id: str,
    metric_name: str,
    unit: str,
    source_name: str,
    source_url: str,
    higher_is_better: bool,
    category: str,
    yearly_values: dict[int, dict[str, float]],
    notes_by_year: dict[int, str] | None = None,
) -> list[dict[str, object]]:
    notes_by_year = notes_by_year or {}
    rows: list[dict[str, object]] = []

    for year, values_by_country in sorted(yearly_values.items()):
        for country_code, value in values_by_country.items():
            country_meta = COUNTRIES[country_code]
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_meta["country_name"],
                    "metric_id": metric_id,
                    "metric_name": metric_name,
                    "value": float(value),
                    "year": int(year),
                    "unit": unit,
                    "source_name": source_name,
                    "source_url": source_url,
                    "higher_is_better": higher_is_better,
                    "category": category,
                    "dataset_version": DATASET_VERSION,
                    "region": country_meta["region"],
                    "income_group": country_meta["income_group"],
                    "notes": notes_by_year.get(year),
                }
            )

    return rows


def build_example_metric_dataframe() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for metric_id, metric_meta in METRICS.items():
        rows.extend(
            _build_metric_rows(
                metric_id=metric_id,
                metric_name=str(metric_meta["metric_name"]),
                unit=str(metric_meta["unit"]),
                source_name=str(metric_meta["source_name"]),
                source_url=str(metric_meta["source_url"]),
                higher_is_better=bool(metric_meta["higher_is_better"]),
                category=str(metric_meta["category"]),
                yearly_values=dict(metric_meta["yearly_values"]),
                notes_by_year=dict(metric_meta.get("notes_by_year", {})),
            )
        )

    df = pd.DataFrame(rows)
    df = normalize_canonical_columns(df)
    df = coerce_to_canonical_dtypes(df)
    return df


def build_example_metric_dataset():
    df = build_example_metric_dataframe()
    return validate_and_parse_dataframe(df)
