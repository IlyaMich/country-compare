from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from country_compare.output.tables import (
    make_multi_metric_long_table,
    make_multi_metric_wide_table,
    make_single_metric_table,
    make_weighted_score_table,
)


def _single_metric_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_code": ["SGP", "DEU", "ISR"],
            "country_name": ["Singapore", "Germany", "Israel"],
            "metric_id": ["gdp_per_capita"] * 3,
            "metric_name": ["GDP per capita"] * 3,
            "value": [145000.0, 67000.0, 56000.0],
            "normalized_value": [1.0, 0.1264, 0.0],
            "rank": [1, 2, 3],
            "year": [2023, 2023, 2023],
            "unit": ["USD", "USD", "USD"],
            "normalization_method": ["minmax"] * 3,
            "normalization_basis": ["metric_slice"] * 3,
            "rank_method": ["min"] * 3,
            "extra_column": ["x", "y", "z"],
        }
    )



def _multi_metric_long_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_code": ["ISR", "DEU", "SGP", "ISR", "DEU", "SGP"],
            "country_name": ["Israel", "Germany", "Singapore", "Israel", "Germany", "Singapore"],
            "metric_id": [
                "gdp_per_capita",
                "gdp_per_capita",
                "gdp_per_capita",
                "rule_of_law",
                "rule_of_law",
                "rule_of_law",
            ],
            "metric_name": [
                "GDP per capita",
                "GDP per capita",
                "GDP per capita",
                "Rule of Law",
                "Rule of Law",
                "Rule of Law",
            ],
            "value": [56000.0, 67000.0, 145000.0, 0.67, 0.84, 0.83],
            "normalized_value": [0.0, 0.1264, 1.0, 0.0, 1.0, 0.9412],
            "rank": [3, 2, 1, 3, 1, 2],
            "year": [2023, 2023, 2023, 2022, 2022, 2022],
            "unit": ["USD", "USD", "USD", "index", "index", "index"],
            "category": ["economy", "economy", "economy", "governance", "governance", "governance"],
            "normalization_method": ["minmax"] * 6,
            "normalization_basis": ["metric_slice"] * 6,
            "rank_method": ["min"] * 6,
        }
    )



def _multi_metric_wide_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_code": ["DEU", "ISR", "SGP"],
            "country_name": ["Germany", "Israel", "Singapore"],
            "gdp_per_capita__value": [67000.0, 56000.0, 145000.0],
            "gdp_per_capita__normalized_value": [0.1264, 0.0, 1.0],
            "gdp_per_capita__rank": [2, 3, 1],
            "gdp_per_capita__year": [2023, 2023, 2023],
            "rule_of_law__value": [0.84, 0.67, 0.83],
            "rule_of_law__normalized_value": [1.0, 0.0, 0.9412],
            "rule_of_law__rank": [1, 3, 2],
            "rule_of_law__year": [2022, 2022, 2022],
        }
    )



def _weighted_score_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_code": ["DEU", "SGP", "ISR"],
            "country_name": ["Germany", "Singapore", "Israel"],
            "weighted_score": [0.71, 0.68, 0.22],
            "score_rank": [1, 2, 3],
            "score_rank_method": ["min", "min", "min"],
            "metric_count_used": [3, 3, 3],
            "metric_count_expected": [3, 3, 3],
            "missing_metric_count": [0, 0, 0],
            "missing_metrics": ["", "", ""],
            "weight_sum_used": [1.0, 1.0, 1.0],
            "missing_data_policy": ["renormalize_weights"] * 3,
            "profile_name": ["default"] * 3,
            "year_strategy": ["latest_per_metric"] * 3,
        }
    )



def test_make_single_metric_table_formats_and_sorts() -> None:
    source = _single_metric_df()

    result = make_single_metric_table(
        source,
        rename_columns={"country_name": "country"},
        round_ndigits={"normalized_value": 2},
        top_n=2,
    )

    assert list(result.columns)[:5] == [
        "country_code",
        "country",
        "metric_id",
        "metric_name",
        "value",
    ]
    assert result["country"].tolist() == ["Singapore", "Germany"]
    assert result["normalized_value"].tolist() == [1.0, 0.13]



def test_make_multi_metric_long_table_formats_and_filters_columns() -> None:
    source = _multi_metric_long_df()

    result = make_multi_metric_long_table(
        source,
        columns=["metric_name", "country_name", "normalized_value", "rank"],
        sort_by=["metric_name", "rank"],
        round_ndigits=3,
    )

    assert list(result.columns) == ["metric_name", "country_name", "normalized_value", "rank"]
    assert result.iloc[0].to_dict() == {
        "metric_name": "GDP per capita",
        "country_name": "Singapore",
        "normalized_value": 1.0,
        "rank": 1,
    }



def test_make_multi_metric_wide_table_orders_identifier_columns_first() -> None:
    source = _multi_metric_wide_df()

    result = make_multi_metric_wide_table(source, round_ndigits=2)

    assert result.columns[0] == "country_code"
    assert result.columns[1] == "country_name"
    assert result.iloc[0]["country_name"] == "Germany"
    assert result["rule_of_law__normalized_value"].tolist() == [1.0, 0.0, 0.94]



def test_make_weighted_score_table_formats_and_limits_rows() -> None:
    source = _weighted_score_df()

    result = make_weighted_score_table(
        source,
        columns=["country_name", "weighted_score", "score_rank", "profile_name"],
        rename_columns={"country_name": "country"},
        top_n=2,
    )

    assert list(result.columns) == ["country", "weighted_score", "score_rank", "profile_name"]
    assert result["country"].tolist() == ["Germany", "Singapore"]



def test_table_helpers_do_not_mutate_inputs() -> None:
    source = _single_metric_df()
    original = source.copy(deep=True)

    _ = make_single_metric_table(source, rename_columns={"country_name": "country"}, round_ndigits=2)

    assert_frame_equal(source, original)



def test_single_metric_table_raises_for_missing_columns() -> None:
    source = _single_metric_df().drop(columns=["rank"])

    with pytest.raises(ValueError, match="single metric table requires columns"):
        make_single_metric_table(source)



def test_multi_metric_wide_table_raises_without_identifier_columns() -> None:
    source = _multi_metric_wide_df().drop(columns=["country_code", "country_name"])

    with pytest.raises(ValueError, match="requires at least one"):
        make_multi_metric_wide_table(source)



def test_weighted_score_table_raises_for_missing_sort_column() -> None:
    source = _weighted_score_df()

    with pytest.raises(ValueError, match="cannot sort by missing columns"):
        make_weighted_score_table(source, sort_by="does_not_exist")
