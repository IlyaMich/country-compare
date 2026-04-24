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
            2018: {"ISR": 48000.0, "DEU": 59000.0, "SGP": 120000.0, "CAN": 52000.0, "JPN": 39000.0},
            2019: {"ISR": 49500.0, "DEU": 60500.0, "SGP": 124000.0, "CAN": 53500.0, "JPN": 39800.0},
            2020: {"ISR": 47000.0, "DEU": 58000.0, "SGP": 118000.0, "CAN": 50000.0, "JPN": 38100.0},
            2021: {"ISR": 51000.0, "DEU": 62000.0, "SGP": 132000.0, "CAN": 56000.0, "JPN": 40500.0},
            2022: {"ISR": 54000.0, "DEU": 65000.0, "SGP": 140000.0, "CAN": 59000.0, "JPN": 42000.0},
            2023: {"ISR": 56000.0, "DEU": 67000.0, "SGP": 145000.0, "CAN": 61000.0, "JPN": 43500.0},
            2024: {"ISR": 57500.0, "DEU": 68000.0, "SGP": 149000.0, "CAN": 62500.0, "JPN": 44300.0},
            2025: {"ISR": 59000.0, "DEU": 69500.0, "SGP": 153000.0, "CAN": 64000.0, "JPN": 45000.0},
        },
        "notes_by_year": {
            2020: "Synthetic recession dip for trend-testing.",
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
            2018: {"ISR": 0.70, "DEU": 0.82, "SGP": 0.81, "CAN": 0.89, "JPN": 0.77},
            2019: {"ISR": 0.69, "DEU": 0.82, "SGP": 0.82, "CAN": 0.90, "JPN": 0.78},
            2020: {"ISR": 0.68, "DEU": 0.83, "SGP": 0.82, "CAN": 0.90, "JPN": 0.78},
            2021: {"ISR": 0.68, "DEU": 0.83, "SGP": 0.83, "CAN": 0.91, "JPN": 0.79},
            2022: {"ISR": 0.67, "DEU": 0.84, "SGP": 0.83, "CAN": 0.91, "JPN": 0.79},
            2023: {"ISR": 0.66, "DEU": 0.85, "SGP": 0.84, "CAN": 0.92, "JPN": 0.80},
            2024: {"ISR": 0.66, "DEU": 0.85, "SGP": 0.84, "CAN": 0.92, "JPN": 0.80},
            2025: {"ISR": 0.65, "DEU": 0.86, "SGP": 0.85, "CAN": 0.93, "JPN": 0.81},
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
            2018: {"ISR": 7.9, "DEU": 8.7, "SGP": 6.0, "CAN": 9.1, "JPN": 8.0},
            2019: {"ISR": 7.8, "DEU": 8.7, "SGP": 6.1, "CAN": 9.1, "JPN": 8.1},
            2020: {"ISR": 7.6, "DEU": 8.6, "SGP": 6.0, "CAN": 9.0, "JPN": 8.0},
            2021: {"ISR": 7.7, "DEU": 8.7, "SGP": 6.1, "CAN": 9.0, "JPN": 8.1},
            2022: {"ISR": 7.8, "DEU": 8.8, "SGP": 6.2, "CAN": 9.0, "JPN": 8.2},
            2023: {"ISR": 7.6, "DEU": 8.8, "SGP": 6.3, "CAN": 9.0, "JPN": 8.1},
            2024: {"ISR": 7.5, "DEU": 8.7, "SGP": 6.3, "CAN": 8.9, "JPN": 8.1},
            2025: {"ISR": 7.4, "DEU": 8.7, "SGP": 6.4, "CAN": 8.9, "JPN": 8.0},
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
            2018: {"ISR": 0.8, "DEU": 1.7, "SGP": 0.4, "CAN": 2.3, "JPN": 1.0},
            2019: {"ISR": 0.6, "DEU": 1.4, "SGP": 0.6, "CAN": 1.9, "JPN": 0.5},
            2020: {"ISR": -0.6, "DEU": 0.4, "SGP": -0.2, "CAN": 0.7, "JPN": 0.0},
            2021: {"ISR": 1.5, "DEU": 3.1, "SGP": 2.3, "CAN": 3.4, "JPN": -0.2},
            2022: {"ISR": 4.4, "DEU": 6.9, "SGP": 6.1, "CAN": 6.8, "JPN": 2.5},
            2023: {"ISR": 3.1, "DEU": 5.9, "SGP": 4.8, "CAN": 3.9, "JPN": 3.2},
            2024: {"ISR": 2.4, "DEU": 2.8, "SGP": 2.7, "CAN": 2.5, "JPN": 2.1},
            2025: {"ISR": 2.0, "DEU": 2.3, "SGP": 2.2, "CAN": 2.1, "JPN": 1.8},
        },
        "notes_by_year": {
            2020: "Includes a synthetic low-inflation year to test reversals.",
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
            2018: {"ISR": 82.3, "DEU": 80.6, "SGP": 83.2, "CAN": 82.0, "JPN": 84.2},
            2019: {"ISR": 82.5, "DEU": 80.7, "SGP": 83.3, "CAN": 82.1, "JPN": 84.3},
            2020: {"ISR": 82.1, "DEU": 80.2, "SGP": 83.0, "CAN": 81.8, "JPN": 84.1},
            2021: {"ISR": 82.4, "DEU": 80.5, "SGP": 83.2, "CAN": 82.0, "JPN": 84.2},
            2022: {"ISR": 82.7, "DEU": 80.8, "SGP": 83.5, "CAN": 82.3, "JPN": 84.4},
            2023: {"ISR": 82.9, "DEU": 81.0, "SGP": 83.8, "CAN": 82.5, "JPN": 84.6},
            2024: {"ISR": 83.0, "DEU": 81.1, "SGP": 84.0, "CAN": 82.6, "JPN": 84.7},
            2025: {"ISR": 83.1, "DEU": 81.2, "SGP": 84.1, "CAN": 82.7, "JPN": 84.8},
        },
        "notes_by_year": {
            2020: "Synthetic dip to make recovery behavior visible in forecasts.",
        },
    },
}


DATASET_VERSION = "v0.3.0"


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
