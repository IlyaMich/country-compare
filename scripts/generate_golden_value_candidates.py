from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

DEFAULT_COUNTRIES = ["ISR", "USA", "FRA", "DEU", "GBR", "CAN", "JPN", "SGP"]

DEFAULT_METRICS = [
    "gdp_current_usd",
    "gdp_per_capita",
    "internet_users_pct",
    "unemployment_pct",
    "labor_participation_pct",
    "life_expectancy",
    "life_expectancy_female",
    "life_expectancy_male",
    "population_growth_pct",
    "education_spending_pct_gdp",
    "rnd_expenditure_pct_gdp",
    "crude_death_rate",
    "consumer_price_index",
    "inflation",
    "rule_of_law",
    "democracy_index",
]


def _parse_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None or not value.strip():
        return default

    return [item.strip() for item in value.split(",") if item.strip()]


def _source_contains(value: object) -> list[str]:
    text = str(value)

    if "world bank" in text.lower():
        return ["World Bank"]

    if "example" in text.lower():
        return ["Example Source"]

    return [text]


def _url_contains(value: object) -> list[str]:
    text = str(value)

    if "worldbank.org" in text.lower():
        return ["worldbank.org"]

    if "api.worldbank.org" in text.lower():
        return ["api.worldbank.org"]

    if "data.worldbank.org" in text.lower():
        return ["data.worldbank.org"]

    if "example.org" in text.lower():
        return ["example.org"]

    return [text]


def _default_tolerance(row: pd.Series) -> dict[str, float]:
    unit = str(row["unit"])
    metric_id = str(row["metric_id"])

    if unit in {"USD", "LCU", "count"}:
        return {"tolerance_pct": 1.0}

    if unit == "percent":
        return {"tolerance_abs": 0.25}

    if unit == "years":
        return {"tolerance_abs": 0.1}

    if unit in {"index", "score_0_10", "index_2010_100", "per_1000_people"}:
        return {"tolerance_abs": 0.01}

    if metric_id.endswith("_pct"):
        return {"tolerance_abs": 0.25}

    return {"tolerance_pct": 1.0}


def generate_candidates(
    *,
    data_path: Path,
    countries: list[str],
    metrics: list[str],
    max_per_metric: int,
    prefer_year: int | None,
) -> list[dict[str, object]]:
    dataframe = pd.read_parquet(data_path).copy()
    dataframe["year"] = pd.to_numeric(dataframe["year"], errors="coerce")
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")

    dataframe = dataframe[
        dataframe["country_code"].astype(str).isin(countries)
        & dataframe["metric_id"].astype(str).isin(metrics)
        & dataframe["year"].notna()
        & dataframe["value"].notna()
    ]

    if dataframe.empty:
        return []

    candidates: list[dict[str, object]] = []

    for _metric_id, metric_rows in dataframe.groupby("metric_id"):
        selected_rows: list[pd.Series] = []

        if prefer_year is not None:
            preferred = metric_rows[metric_rows["year"].astype(int) == prefer_year]
            for _, row in (
                preferred.sort_values("country_code").head(max_per_metric).iterrows()
            ):
                selected_rows.append(row)

        if len(selected_rows) < max_per_metric:
            latest_rows = (
                metric_rows.sort_values(["country_code", "year"])
                .groupby("country_code", as_index=False)
                .tail(1)
                .sort_values(["metric_id", "country_code"])
            )

            for _, row in latest_rows.iterrows():
                key = (
                    str(row["country_code"]),
                    str(row["metric_id"]),
                    int(row["year"]),
                )
                existing_keys = {
                    (
                        str(existing["country_code"]),
                        str(existing["metric_id"]),
                        int(existing["year"]),
                    )
                    for existing in selected_rows
                }

                if key not in existing_keys:
                    selected_rows.append(row)

                if len(selected_rows) >= max_per_metric:
                    break

        for row in selected_rows[:max_per_metric]:
            tolerance = _default_tolerance(row)

            candidates.append(
                {
                    "country_code": str(row["country_code"]),
                    "metric_id": str(row["metric_id"]),
                    "year": int(row["year"]),
                    "expected_value": float(row["value"]),
                    **tolerance,
                    "unit": str(row["unit"]),
                    "category": str(row["category"]),
                    "higher_is_better": bool(row["higher_is_better"]),
                    "source_name_contains": _source_contains(row["source_name"]),
                    "source_url_contains": _url_contains(row["source_url"]),
                    "review_status": "needs_source_verification",
                }
            )

    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate candidate release golden values from a canonical parquet dataset."
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path("data/processed/metrics.parquet"),
    )
    parser.add_argument(
        "--countries",
        default=None,
        help="Comma-separated country codes. Defaults to common release/demo countries.",
    )
    parser.add_argument(
        "--metrics",
        default=None,
        help="Comma-separated metric IDs. Defaults to common release-critical metrics.",
    )
    parser.add_argument(
        "--max-per-metric",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--prefer-year",
        type=int,
        default=None,
        help="Prefer this year when available; otherwise use latest available rows.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/data/golden_value_candidates.yaml"),
    )

    args = parser.parse_args()

    candidates = generate_candidates(
        data_path=args.data_path,
        countries=_parse_csv(args.countries, DEFAULT_COUNTRIES),
        metrics=_parse_csv(args.metrics, DEFAULT_METRICS),
        max_per_metric=args.max_per_metric,
        prefer_year=args.prefer_year,
    )

    payload = {
        "release_dataset": {
            "golden_values": candidates,
        }
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    print(f"Wrote {len(candidates)} candidate golden values to {args.output}")
    print(
        "Review each value against the original source before copying into golden_values.yaml."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
