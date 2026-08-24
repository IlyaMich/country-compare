from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from country_compare.comparison.multi_metric import compare_countries
from country_compare.comparison.single_metric import (
    RANK_COLUMN,
    RANK_METHOD_COLUMN,
    compare_metric,
)
from country_compare.config.models import (
    ConfigurationBundle,
    MetricConfig,
    MetricsConfig,
    MissingDataPolicy,
    NormalizationMethod,
    ScoringConfig,
    ScoringProfile,
    WeightHandlingStrategy,
    YearStrategy,
)
from country_compare.metrics.normalization import (
    NORMALIZATION_BASIS_COLUMN,
    NORMALIZATION_METHOD_COLUMN,
    NORMALIZED_VALUE_COLUMN,
    normalize_metric,
)
from country_compare.scoring.weighted_score import score_countries
from country_compare.services.comparison_service import ComparisonService
from country_compare.services.requests import SingleMetricRequest

pytestmark = pytest.mark.unit

METRIC_ID = "oracle_metric"
YEAR = 2023


def _oracle_dataframe(
    values: dict[str, float],
    *,
    higher_is_better: bool,
) -> pd.DataFrame:
    """
    Build a deliberately tiny canonical dataset for mathematical oracle tests.

    Expected values in the tests must be calculated independently and
    hard-coded. Do not use Country Compare normalization/ranking functions
    to construct the expected results.
    """
    country_names = {
        "AAA": "Country A",
        "BBB": "Country B",
        "CCC": "Country C",
    }

    records: list[dict[str, object]] = []

    for country_code, value in values.items():
        records.append(
            {
                "country_code": country_code,
                "country_name": country_names[country_code],
                "metric_id": METRIC_ID,
                "metric_name": "Oracle Metric",
                "value": float(value),
                "year": YEAR,
                "unit": "oracle_units",
                "source_name": "Independent Oracle Fixture",
                "source_url": "https://example.invalid/oracle",
                "higher_is_better": higher_is_better,
                "category": "oracle",
                "dataset_version": "oracle-v1",
                "region": "Oracle Region",
                "income_group": "Oracle Income",
                "notes": None,
            }
        )

    return pd.DataFrame.from_records(records)


def _oracle_record(
    *,
    country_code: str,
    value: float,
    year: int,
    metric_id: str = METRIC_ID,
    higher_is_better: bool = True,
) -> dict[str, object]:
    country_names = {
        "AAA": "Country A",
        "BBB": "Country B",
        "CCC": "Country C",
    }

    return {
        "country_code": country_code,
        "country_name": country_names[country_code],
        "metric_id": metric_id,
        "metric_name": (
            "Oracle Metric" if metric_id == METRIC_ID else "Support Metric"
        ),
        "value": float(value),
        "year": year,
        "unit": "oracle_units",
        "source_name": "Independent Oracle Fixture",
        "source_url": "https://example.invalid/oracle",
        "higher_is_better": higher_is_better,
        "category": "oracle",
        "dataset_version": "oracle-v1",
        "region": "Oracle Region",
        "income_group": "Oracle Income",
        "notes": None,
    }


def _result_by_country(
    dataframe: pd.DataFrame,
) -> dict[str, dict[str, object]]:
    return {str(row["country_code"]): row.to_dict() for _, row in dataframe.iterrows()}


def _validation_oracle_metric_rows(
    *,
    metric_id: str,
    values: dict[str, float],
    higher_is_better: bool,
) -> list[dict[str, object]]:
    country_names = {
        "AAA": "Alpha",
        "BBB": "Beta",
        "CCC": "Gamma",
    }

    return [
        {
            "country_code": country_code,
            "country_name": country_names[country_code],
            "metric_id": metric_id,
            "metric_name": metric_id.replace("_", " ").title(),
            "value": float(value),
            "year": 2023,
            "unit": "oracle_unit",
            "source_name": "Validation oracle",
            "source_url": "https://example.test/validation-oracle",
            "higher_is_better": higher_is_better,
            "category": "validation",
        }
        for country_code, value in values.items()
    ]


def _validation_oracle_scoring_configs(
    *,
    missing_data_policy: MissingDataPolicy,
) -> tuple[MetricsConfig, ScoringConfig]:
    metrics_config = MetricsConfig(
        metrics={
            "metric_alpha": MetricConfig(
                display_name="Metric Alpha",
                category="validation",
                higher_is_better=True,
                default_weight=0.6,
                unit="oracle_unit",
                normalization_method=NormalizationMethod.MINMAX,
            ),
            "metric_beta": MetricConfig(
                display_name="Metric Beta",
                category="validation",
                higher_is_better=True,
                default_weight=0.4,
                unit="oracle_unit",
                normalization_method=NormalizationMethod.MINMAX,
            ),
        }
    )

    scoring_config = ScoringConfig(
        default_profile="oracle_profile",
        weight_handling=WeightHandlingStrategy.NORMALIZE,
        default_year_strategy=YearStrategy.LATEST_PER_METRIC,
        default_missing_data_policy=missing_data_policy,
        profiles={
            "oracle_profile": ScoringProfile(
                metrics=["metric_alpha", "metric_beta"],
                weights={
                    "metric_alpha": 0.6,
                    "metric_beta": 0.4,
                },
                normalization_overrides={
                    "metric_alpha": NormalizationMethod.MINMAX,
                    "metric_beta": NormalizationMethod.MINMAX,
                },
                year_strategy=YearStrategy.LATEST_PER_METRIC,
                missing_data_policy=missing_data_policy,
            )
        },
    )

    return metrics_config, scoring_config


def _validation_oracle_weighted_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            *_validation_oracle_metric_rows(
                metric_id="metric_alpha",
                values={"AAA": 10.0, "BBB": 20.0, "CCC": 30.0},
                higher_is_better=True,
            ),
            *_validation_oracle_metric_rows(
                metric_id="metric_beta",
                values={"AAA": 30.0, "BBB": 10.0, "CCC": 20.0},
                higher_is_better=True,
            ),
        ]
    )


class _OracleComparisonService(ComparisonService):
    def __init__(
        self,
        dataframe: pd.DataFrame,
        bundle: ConfigurationBundle,
    ) -> None:
        super().__init__(context=SimpleNamespace())
        self._oracle_dataframe = dataframe.copy(deep=True)
        self._oracle_bundle = bundle

    def _load_dataframe(self) -> pd.DataFrame:
        return self._oracle_dataframe.copy(deep=True)

    def _load_configuration_bundle(self) -> ConfigurationBundle:
        return self._oracle_bundle


def _oracle_bundle() -> ConfigurationBundle:
    metrics = MetricsConfig(
        metrics={
            METRIC_ID: MetricConfig(
                display_name="Oracle Metric",
                category="oracle",
                higher_is_better=True,
                default_weight=1.0,
                unit="oracle_units",
                normalization_method=NormalizationMethod.MINMAX,
            ),
        }
    )

    scoring = ScoringConfig(
        default_profile="default",
        profiles={
            "default": ScoringProfile(
                metrics=[METRIC_ID],
                description="Oracle validation profile",
            ),
        },
    )

    return ConfigurationBundle(
        metrics=metrics,
        scoring=scoring,
    )


def test_cmp_01_higher_is_better_minmax_and_ranks() -> None:
    """
    CMP-01

    Independent oracle:

        raw values:
            AAA = 10
            BBB = 20
            CCC = 30

        min-max scores:
            AAA = (10 - 10) / (30 - 10) = 0.0
            BBB = (20 - 10) / (30 - 10) = 0.5
            CCC = (30 - 10) / (30 - 10) = 1.0

        higher-is-better ranking:
            CCC = rank 1
            BBB = rank 2
            AAA = rank 3
    """
    dataframe = _oracle_dataframe(
        {
            "AAA": 10.0,
            "BBB": 20.0,
            "CCC": 30.0,
        },
        higher_is_better=True,
    )

    result = compare_metric(
        dataframe,
        metric_id=METRIC_ID,
        normalization_method=NormalizationMethod.MINMAX,
    )

    expected_normalized = {
        "AAA": 0.0,
        "BBB": 0.5,
        "CCC": 1.0,
    }
    expected_ranks = {
        "AAA": 3,
        "BBB": 2,
        "CCC": 1,
    }

    actual = _result_by_country(result)

    assert set(actual) == set(expected_normalized)

    for country_code in expected_normalized:
        assert actual[country_code][NORMALIZED_VALUE_COLUMN] == pytest.approx(
            expected_normalized[country_code]
        )
        assert actual[country_code][RANK_COLUMN] == expected_ranks[country_code]

    assert result["country_code"].tolist() == ["CCC", "BBB", "AAA"]
    assert result[NORMALIZATION_METHOD_COLUMN].tolist() == ["minmax"] * 3
    assert result[NORMALIZATION_BASIS_COLUMN].tolist() == ["metric_slice"] * 3
    assert result[RANK_METHOD_COLUMN].tolist() == ["competition_min"] * 3


def test_cmp_02_lower_is_better_reverses_minmax_and_ranks() -> None:
    """
    CMP-02

    Start with the same raw min-max scores as CMP-01:

        AAA = 0.0
        BBB = 0.5
        CCC = 1.0

    lower-is-better reverses them:

        AAA = 1.0
        BBB = 0.5
        CCC = 0.0

    Therefore:

        AAA = rank 1
        BBB = rank 2
        CCC = rank 3
    """
    dataframe = _oracle_dataframe(
        {
            "AAA": 10.0,
            "BBB": 20.0,
            "CCC": 30.0,
        },
        higher_is_better=False,
    )

    result = compare_metric(
        dataframe,
        metric_id=METRIC_ID,
        normalization_method=NormalizationMethod.MINMAX,
    )

    expected_normalized = {
        "AAA": 1.0,
        "BBB": 0.5,
        "CCC": 0.0,
    }
    expected_ranks = {
        "AAA": 1,
        "BBB": 2,
        "CCC": 3,
    }

    actual = _result_by_country(result)

    for country_code in expected_normalized:
        assert actual[country_code][NORMALIZED_VALUE_COLUMN] == pytest.approx(
            expected_normalized[country_code]
        )
        assert actual[country_code][RANK_COLUMN] == expected_ranks[country_code]

    assert result["country_code"].tolist() == ["AAA", "BBB", "CCC"]


def test_cmp_03_ties_use_competition_ranking() -> None:
    """
    CMP-03

    Independent oracle:

        AAA = 30
        BBB = 30
        CCC = 10

    With higher-is-better min-max:

        AAA = 1.0
        BBB = 1.0
        CCC = 0.0

    Competition ranking must be:

        1, 1, 3

    Rank 2 is skipped because two countries occupy first place.
    """
    dataframe = _oracle_dataframe(
        {
            "AAA": 30.0,
            "BBB": 30.0,
            "CCC": 10.0,
        },
        higher_is_better=True,
    )

    result = compare_metric(
        dataframe,
        metric_id=METRIC_ID,
        normalization_method=NormalizationMethod.MINMAX,
    )

    actual = _result_by_country(result)

    assert actual["AAA"][NORMALIZED_VALUE_COLUMN] == pytest.approx(1.0)
    assert actual["BBB"][NORMALIZED_VALUE_COLUMN] == pytest.approx(1.0)
    assert actual["CCC"][NORMALIZED_VALUE_COLUMN] == pytest.approx(0.0)

    assert actual["AAA"][RANK_COLUMN] == 1
    assert actual["BBB"][RANK_COLUMN] == 1
    assert actual["CCC"][RANK_COLUMN] == 3

    assert sorted(result[RANK_COLUMN].tolist()) == [1, 1, 3]

    # Equal scores are displayed deterministically using country name/code
    # as the tie breaker.
    assert result["country_code"].tolist() == ["AAA", "BBB", "CCC"]


def test_cmp_04_minmax_formula_matches_independent_oracle() -> None:
    """
    CMP-04

    Validate normalization directly, without involving ranking.

    Input is intentionally not ordered by value:

        AAA = 30
        BBB = 10
        CCC = 20

    Independent min-max calculations:

        AAA = (30 - 10) / 20 = 1.0
        BBB = (10 - 10) / 20 = 0.0
        CCC = (20 - 10) / 20 = 0.5
    """
    dataframe = _oracle_dataframe(
        {
            "AAA": 30.0,
            "BBB": 10.0,
            "CCC": 20.0,
        },
        higher_is_better=True,
    )

    result = normalize_metric(
        dataframe,
        method=NormalizationMethod.MINMAX,
    )

    actual = result.set_index("country_code")[NORMALIZED_VALUE_COLUMN].to_dict()

    assert actual["AAA"] == pytest.approx(1.0)
    assert actual["BBB"] == pytest.approx(0.0)
    assert actual["CCC"] == pytest.approx(0.5)

    # Normalization itself must not reorder rows.
    assert result["country_code"].tolist() == ["AAA", "BBB", "CCC"]

    assert result[NORMALIZATION_METHOD_COLUMN].tolist() == ["minmax"] * 3
    assert result[NORMALIZATION_BASIS_COLUMN].tolist() == ["metric_slice"] * 3


def test_cmp_05_percentile_normalization_and_direction() -> None:
    """
    CMP-05

    Independent percentile oracle with a tie.

    Raw values:

        AAA = 10
        BBB = 20
        CCC = 20

    Ascending average ranks:

        AAA = 1.0
        BBB = 2.5
        CCC = 2.5

    Percentile score is:

        (rank - 1) / (N - 1)

    For N = 3:

        AAA = (1.0 - 1) / 2 = 0.0
        BBB = (2.5 - 1) / 2 = 0.75
        CCC = (2.5 - 1) / 2 = 0.75

    For lower-is-better, scores are reversed with 1 - score:

        AAA = 1.0
        BBB = 0.25
        CCC = 0.25
    """
    values = {
        "AAA": 10.0,
        "BBB": 20.0,
        "CCC": 20.0,
    }

    higher_dataframe = _oracle_dataframe(
        values,
        higher_is_better=True,
    )
    lower_dataframe = _oracle_dataframe(
        values,
        higher_is_better=False,
    )

    higher_result = normalize_metric(
        higher_dataframe,
        method=NormalizationMethod.PERCENTILE,
    )
    lower_result = normalize_metric(
        lower_dataframe,
        method=NormalizationMethod.PERCENTILE,
    )

    higher_actual = higher_result.set_index("country_code")[
        NORMALIZED_VALUE_COLUMN
    ].to_dict()
    lower_actual = lower_result.set_index("country_code")[
        NORMALIZED_VALUE_COLUMN
    ].to_dict()

    expected_higher = {
        "AAA": 0.0,
        "BBB": 0.75,
        "CCC": 0.75,
    }
    expected_lower = {
        "AAA": 1.0,
        "BBB": 0.25,
        "CCC": 0.25,
    }

    for country_code, expected in expected_higher.items():
        assert higher_actual[country_code] == pytest.approx(expected)

    for country_code, expected in expected_lower.items():
        assert lower_actual[country_code] == pytest.approx(expected)

    # Normalization must preserve raw data.
    assert higher_result["value"].tolist() == [10.0, 20.0, 20.0]
    assert lower_result["value"].tolist() == [10.0, 20.0, 20.0]

    assert higher_result[NORMALIZATION_METHOD_COLUMN].tolist() == ["percentile"] * 3
    assert lower_result[NORMALIZATION_METHOD_COLUMN].tolist() == ["percentile"] * 3


def test_cmp_06_rank_normalization_handles_positions_direction_and_ties() -> None:
    """
    CMP-06

    Independent rank-normalization oracle.

    Raw values:

        AAA = 10
        BBB = 20
        CCC = 20

    Descending competition ranks:

        BBB = 1
        CCC = 1
        AAA = 3

    Rank normalization is:

        1 - ((rank - 1) / (N - 1))

    Therefore for higher-is-better:

        AAA = 0.0
        BBB = 1.0
        CCC = 1.0

    For lower-is-better, scores reverse:

        AAA = 1.0
        BBB = 0.0
        CCC = 0.0
    """
    values = {
        "AAA": 10.0,
        "BBB": 20.0,
        "CCC": 20.0,
    }

    higher_dataframe = _oracle_dataframe(
        values,
        higher_is_better=True,
    )
    lower_dataframe = _oracle_dataframe(
        values,
        higher_is_better=False,
    )

    higher_result = normalize_metric(
        higher_dataframe,
        method=NormalizationMethod.RANK,
    )
    lower_result = normalize_metric(
        lower_dataframe,
        method=NormalizationMethod.RANK,
    )

    higher_actual = higher_result.set_index("country_code")[
        NORMALIZED_VALUE_COLUMN
    ].to_dict()
    lower_actual = lower_result.set_index("country_code")[
        NORMALIZED_VALUE_COLUMN
    ].to_dict()

    expected_higher = {
        "AAA": 0.0,
        "BBB": 1.0,
        "CCC": 1.0,
    }
    expected_lower = {
        "AAA": 1.0,
        "BBB": 0.0,
        "CCC": 0.0,
    }

    for country_code, expected in expected_higher.items():
        assert higher_actual[country_code] == pytest.approx(expected)

    for country_code, expected in expected_lower.items():
        assert lower_actual[country_code] == pytest.approx(expected)

    assert higher_result[NORMALIZATION_METHOD_COLUMN].tolist() == ["rank"] * 3
    assert lower_result[NORMALIZATION_METHOD_COLUMN].tolist() == ["rank"] * 3


def test_cmp_07_log_minmax_matches_oracle_and_rejects_non_positive_values() -> None:
    """
    CMP-07

    Valid independent oracle:

        AAA = 1
        BBB = 10
        CCC = 100

    Natural logs:

        ln(1)   = 0
        ln(10)  = x
        ln(100) = 2x

    Min-max normalization of those logged values therefore gives exactly:

        AAA = 0.0
        BBB = 0.5
        CCC = 1.0

    The method's mathematical domain requires strictly positive values.
    Zero and negative values must be rejected rather than silently
    transformed or assigned fabricated scores.
    """
    valid_dataframe = _oracle_dataframe(
        {
            "AAA": 1.0,
            "BBB": 10.0,
            "CCC": 100.0,
        },
        higher_is_better=True,
    )

    result = normalize_metric(
        valid_dataframe,
        method=NormalizationMethod.LOG_MINMAX,
    )

    actual = result.set_index("country_code")[NORMALIZED_VALUE_COLUMN].to_dict()

    assert actual["AAA"] == pytest.approx(0.0)
    assert actual["BBB"] == pytest.approx(0.5)
    assert actual["CCC"] == pytest.approx(1.0)

    assert (
        result[NORMALIZATION_METHOD_COLUMN].tolist()
        == [NormalizationMethod.LOG_MINMAX.value] * 3
    )
    assert result[NORMALIZATION_BASIS_COLUMN].tolist() == ["metric_slice"] * 3

    for invalid_value in (0.0, -1.0):
        invalid_dataframe = _oracle_dataframe(
            {
                "AAA": 1.0,
                "BBB": invalid_value,
                "CCC": 100.0,
            },
            higher_is_better=True,
        )

        with pytest.raises(
            ValueError,
            match="log-minmax normalization requires strictly positive values",
        ):
            normalize_metric(
                invalid_dataframe,
                method=NormalizationMethod.LOG_MINMAX,
            )


def test_cmp_08_latest_per_metric_selects_each_country_latest_observation() -> None:
    """
    CMP-08

    Independent year-selection oracle.

    Available observations:

        AAA:
            2021 = 10
            2023 = 30

        BBB:
            2020 = 40
            2022 = 20

        CCC:
            2021 = 15
            2023 = 25

    latest_per_metric must independently select:

        AAA -> 2023 / 30
        BBB -> 2022 / 20
        CCC -> 2023 / 25

    It must NOT force all countries onto one common year.
    """
    dataframe = pd.DataFrame.from_records(
        [
            _oracle_record(
                country_code="AAA",
                year=2021,
                value=10.0,
            ),
            _oracle_record(
                country_code="AAA",
                year=2023,
                value=30.0,
            ),
            _oracle_record(
                country_code="BBB",
                year=2020,
                value=40.0,
            ),
            _oracle_record(
                country_code="BBB",
                year=2022,
                value=20.0,
            ),
            _oracle_record(
                country_code="CCC",
                year=2021,
                value=15.0,
            ),
            _oracle_record(
                country_code="CCC",
                year=2023,
                value=25.0,
            ),
        ]
    )

    result = compare_metric(
        dataframe,
        metric_id=METRIC_ID,
        year_strategy=YearStrategy.LATEST_PER_METRIC,
        normalization_method=NormalizationMethod.MINMAX,
    )

    actual = _result_by_country(result)

    assert set(actual) == {"AAA", "BBB", "CCC"}

    assert actual["AAA"]["year"] == 2023
    assert actual["AAA"]["value"] == pytest.approx(30.0)

    assert actual["BBB"]["year"] == 2022
    assert actual["BBB"]["value"] == pytest.approx(20.0)

    assert actual["CCC"]["year"] == 2023
    assert actual["CCC"]["value"] == pytest.approx(25.0)

    # Independent normalization after year selection:
    #
    # selected values = 20, 25, 30
    #
    # BBB = 0.0
    # CCC = 0.5
    # AAA = 1.0
    assert actual["AAA"][NORMALIZED_VALUE_COLUMN] == pytest.approx(1.0)
    assert actual["BBB"][NORMALIZED_VALUE_COLUMN] == pytest.approx(0.0)
    assert actual["CCC"][NORMALIZED_VALUE_COLUMN] == pytest.approx(0.5)

    assert actual["AAA"][RANK_COLUMN] == 1
    assert actual["CCC"][RANK_COLUMN] == 2
    assert actual["BBB"][RANK_COLUMN] == 3


def test_cmp_09_target_year_uses_exact_year_and_reports_missing_country() -> None:
    """
    CMP-09

    Target year = 2022.

    AAA has:
        2021 = 5
        2022 = 10

    BBB has:
        2022 = 20
        2023 = 40

    CCC has:
        2021 = 15
        2023 = 30

    Therefore:
        AAA -> exactly 2022 / 10
        BBB -> exactly 2022 / 20
        CCC -> excluded

    CCC must NOT fall back to either 2021 or 2023.
    The service must visibly report that CCC is absent.
    """
    dataframe = pd.DataFrame.from_records(
        [
            _oracle_record(
                country_code="AAA",
                year=2021,
                value=5.0,
            ),
            _oracle_record(
                country_code="AAA",
                year=2022,
                value=10.0,
            ),
            _oracle_record(
                country_code="BBB",
                year=2022,
                value=20.0,
            ),
            _oracle_record(
                country_code="BBB",
                year=2023,
                value=40.0,
            ),
            _oracle_record(
                country_code="CCC",
                year=2021,
                value=15.0,
            ),
            _oracle_record(
                country_code="CCC",
                year=2023,
                value=30.0,
            ),
        ]
    )

    service = _OracleComparisonService(
        dataframe,
        _oracle_bundle(),
    )

    request = SingleMetricRequest(
        countries=["AAA", "BBB", "CCC"],
        metric_id=METRIC_ID,
        year_strategy=YearStrategy.TARGET_YEAR,
        target_year=2022,
    )

    result = service.run_single_metric(request)

    assert result.ok is True
    assert result.error is None

    actual = _result_by_country(result.dataframe)

    assert set(actual) == {"AAA", "BBB"}

    assert actual["AAA"]["year"] == 2022
    assert actual["AAA"]["value"] == pytest.approx(10.0)

    assert actual["BBB"]["year"] == 2022
    assert actual["BBB"]["value"] == pytest.approx(20.0)

    # CCC has no 2022 observation.
    assert "CCC" not in actual

    # No nearest-year or last-observed substitution.
    returned_values = set(result.dataframe["value"].astype(float).tolist())
    assert returned_values == {10.0, 20.0}

    assert result.metadata["year_strategy"] == "target_year"
    assert result.metadata["target_year"] == 2022
    assert result.metadata["result_row_count"] == 2
    assert result.metadata["years_used"] == [2022]

    assert result.diagnostics["row_count"] == 2

    assert any(
        "CCC" in warning and "not present in the result" in warning
        for warning in result.warnings
    )


def test_cmp_10_missing_metric_observation_is_not_fabricated_as_zero() -> None:
    """
    CMP-10

    AAA and BBB have the requested metric.

    CCC exists in the dataset, but only for an unrelated support metric.

    Selecting AAA, BBB, CCC for oracle_metric must:

        - return real values only for AAA and BBB;
        - not invent oracle_metric=0 for CCC;
        - visibly report CCC as missing from the result.
    """
    dataframe = pd.DataFrame.from_records(
        [
            _oracle_record(
                country_code="AAA",
                year=2023,
                value=10.0,
            ),
            _oracle_record(
                country_code="BBB",
                year=2023,
                value=20.0,
            ),
            # CCC exists in the dataset, which means it is a valid selected
            # country, but it has no observation for METRIC_ID.
            _oracle_record(
                country_code="CCC",
                year=2023,
                value=999.0,
                metric_id="support_metric",
            ),
        ]
    )

    service = _OracleComparisonService(
        dataframe,
        _oracle_bundle(),
    )

    request = SingleMetricRequest(
        countries=["AAA", "BBB", "CCC"],
        metric_id=METRIC_ID,
        year_strategy=YearStrategy.LATEST_PER_METRIC,
    )

    result = service.run_single_metric(request)

    assert result.ok is True
    assert result.error is None

    actual = _result_by_country(result.dataframe)

    assert set(actual) == {"AAA", "BBB"}

    assert actual["AAA"]["value"] == pytest.approx(10.0)
    assert actual["BBB"]["value"] == pytest.approx(20.0)

    assert "CCC" not in actual

    # Most important invariant: absence must never be converted to a
    # fabricated numeric observation.
    assert not (result.dataframe["value"].astype(float).eq(0.0).any())

    assert result.metadata["selected_countries"] == [
        "AAA",
        "BBB",
        "CCC",
    ]
    assert result.metadata["result_row_count"] == 2

    assert any(
        "CCC" in warning and "not present in the result" in warning
        for warning in result.warnings
    )


def test_cmp_11_multi_metric_normalization_and_ranks_match_independent_oracles() -> (
    None
):
    dataframe = pd.DataFrame(
        [
            *_validation_oracle_metric_rows(
                metric_id="metric_alpha",
                values={"AAA": 10.0, "BBB": 20.0, "CCC": 30.0},
                higher_is_better=True,
            ),
            *_validation_oracle_metric_rows(
                metric_id="metric_beta",
                values={"AAA": 90.0, "BBB": 30.0, "CCC": 60.0},
                higher_is_better=True,
            ),
        ]
    )

    result = compare_countries(
        dataframe,
        metric_ids=["metric_alpha", "metric_beta"],
        year_strategy=YearStrategy.TARGET_YEAR,
        target_year=2023,
        normalization_method=NormalizationMethod.MINMAX,
    )

    # Hand-calculated independently:
    #
    # metric_alpha: min=10, max=30
    # AAA -> 0.0, rank 3
    # BBB -> 0.5, rank 2
    # CCC -> 1.0, rank 1
    #
    # metric_beta: min=30, max=90
    # AAA -> 1.0, rank 1
    # BBB -> 0.0, rank 3
    # CCC -> 0.5, rank 2
    expected = {
        ("metric_alpha", "AAA"): (10.0, 0.0, 3),
        ("metric_alpha", "BBB"): (20.0, 0.5, 2),
        ("metric_alpha", "CCC"): (30.0, 1.0, 1),
        ("metric_beta", "AAA"): (90.0, 1.0, 1),
        ("metric_beta", "BBB"): (30.0, 0.0, 3),
        ("metric_beta", "CCC"): (60.0, 0.5, 2),
    }

    assert len(result) == 6
    assert set(zip(result["metric_id"], result["country_code"], strict=True)) == set(
        expected
    )

    for row in result.itertuples(index=False):
        raw_value, normalized_value, rank = expected[(row.metric_id, row.country_code)]

        assert float(row.value) == raw_value
        assert float(row.normalized_value) == pytest.approx(
            normalized_value,
            abs=1e-12,
        )
        assert int(row.rank) == rank
        assert row.normalization_method == "minmax"


def test_cmp_12_multi_metric_applies_direction_independently_per_metric() -> None:
    dataframe = pd.DataFrame(
        [
            *_validation_oracle_metric_rows(
                metric_id="higher_metric",
                values={"AAA": 10.0, "BBB": 20.0, "CCC": 30.0},
                higher_is_better=True,
            ),
            *_validation_oracle_metric_rows(
                metric_id="lower_metric",
                values={"AAA": 10.0, "BBB": 20.0, "CCC": 30.0},
                higher_is_better=False,
            ),
        ]
    )

    result = compare_countries(
        dataframe,
        metric_ids=["higher_metric", "lower_metric"],
        year_strategy=YearStrategy.TARGET_YEAR,
        target_year=2023,
        normalization_method=NormalizationMethod.MINMAX,
    )

    # Both metrics deliberately have identical raw values.
    #
    # higher_metric:
    # AAA -> 0.0 / rank 3
    # BBB -> 0.5 / rank 2
    # CCC -> 1.0 / rank 1
    #
    # lower_metric reverses desirability:
    # AAA -> 1.0 / rank 1
    # BBB -> 0.5 / rank 2
    # CCC -> 0.0 / rank 3
    expected = {
        ("higher_metric", "AAA"): (10.0, 0.0, 3),
        ("higher_metric", "BBB"): (20.0, 0.5, 2),
        ("higher_metric", "CCC"): (30.0, 1.0, 1),
        ("lower_metric", "AAA"): (10.0, 1.0, 1),
        ("lower_metric", "BBB"): (20.0, 0.5, 2),
        ("lower_metric", "CCC"): (30.0, 0.0, 3),
    }

    assert len(result) == 6

    for row in result.itertuples(index=False):
        raw_value, normalized_value, rank = expected[(row.metric_id, row.country_code)]

        # Direction must never alter the raw source value.
        assert float(row.value) == raw_value
        assert float(row.normalized_value) == pytest.approx(
            normalized_value,
            abs=1e-12,
        )
        assert int(row.rank) == rank


def test_cmp_13_weighted_score_matches_independent_complete_data_oracle() -> None:
    dataframe = _validation_oracle_weighted_dataframe()
    metrics_config, scoring_config = _validation_oracle_scoring_configs(
        missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
    )

    result = score_countries(
        dataframe,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name="oracle_profile",
    )

    # Independent calculations:
    #
    # metric_alpha normalized:
    # AAA=0.0, BBB=0.5, CCC=1.0
    #
    # metric_beta normalized:
    # AAA=1.0, BBB=0.0, CCC=0.5
    #
    # weights alpha=0.6, beta=0.4
    #
    # AAA = 0.0*0.6 + 1.0*0.4 = 0.4
    # BBB = 0.5*0.6 + 0.0*0.4 = 0.3
    # CCC = 1.0*0.6 + 0.5*0.4 = 0.8
    expected = {
        "AAA": (0.4, 2),
        "BBB": (0.3, 3),
        "CCC": (0.8, 1),
    }

    assert list(result["country_code"]) == ["CCC", "AAA", "BBB"]

    for row in result.itertuples(index=False):
        expected_score, expected_rank = expected[row.country_code]

        assert float(row.weighted_score) == pytest.approx(
            expected_score,
            abs=1e-12,
        )
        assert int(row.score_rank) == expected_rank
        assert int(row.metric_count_used) == 2
        assert int(row.metric_count_expected) == 2
        assert int(row.missing_metric_count) == 0
        assert float(row.weight_sum_used) == pytest.approx(1.0, abs=1e-12)


def test_cmp_14_missing_metric_renormalizes_remaining_weight_exactly() -> None:
    dataframe = _validation_oracle_weighted_dataframe()

    dataframe = dataframe.loc[
        ~(
            (dataframe["country_code"] == "BBB")
            & (dataframe["metric_id"] == "metric_beta")
        )
    ].copy()

    metrics_config, scoring_config = _validation_oracle_scoring_configs(
        missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
    )

    result = score_countries(
        dataframe,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name="oracle_profile",
    )

    by_country = result.set_index("country_code")

    # metric_alpha still normalizes AAA/BBB/CCC to 0.0/0.5/1.0.
    #
    # BBB has only metric_alpha.
    # Its original alpha weight is 0.6.
    # Renormalized effective alpha weight = 0.6 / 0.6 = 1.0.
    #
    # BBB score = 0.5 * 1.0 = 0.5.
    bbb = by_country.loc["BBB"]

    assert float(bbb["weighted_score"]) == pytest.approx(0.5, abs=1e-12)
    assert int(bbb["metric_count_used"]) == 1
    assert int(bbb["metric_count_expected"]) == 2
    assert int(bbb["missing_metric_count"]) == 1
    assert str(bbb["missing_metrics"]) == "metric_beta"
    assert float(bbb["weight_sum_used"]) == pytest.approx(1.0, abs=1e-12)
    assert bbb["missing_data_policy"] == "renormalize_weights"

    # metric_beta now contains AAA=30 and CCC=20 -> normalized AAA=1, CCC=0.
    #
    # AAA = 0.0*0.6 + 1.0*0.4 = 0.4
    # BBB = 0.5*1.0           = 0.5
    # CCC = 1.0*0.6 + 0.0*0.4 = 0.6
    assert float(by_country.loc["AAA", "weighted_score"]) == pytest.approx(
        0.4,
        abs=1e-12,
    )
    assert float(by_country.loc["CCC", "weighted_score"]) == pytest.approx(
        0.6,
        abs=1e-12,
    )

    assert int(by_country.loc["CCC", "score_rank"]) == 1
    assert int(by_country.loc["BBB", "score_rank"]) == 2
    assert int(by_country.loc["AAA", "score_rank"]) == 3


def test_cmp_15_drop_country_policy_excludes_incomplete_country() -> None:
    dataframe = _validation_oracle_weighted_dataframe()

    dataframe = dataframe.loc[
        ~(
            (dataframe["country_code"] == "BBB")
            & (dataframe["metric_id"] == "metric_beta")
        )
    ].copy()

    metrics_config, scoring_config = _validation_oracle_scoring_configs(
        missing_data_policy=MissingDataPolicy.DROP_COUNTRY,
    )

    result = score_countries(
        dataframe,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name="oracle_profile",
    )

    assert set(result["country_code"]) == {"AAA", "CCC"}
    assert "BBB" not in set(result["country_code"])
    assert set(result["missing_data_policy"]) == {"drop_country"}

    by_country = result.set_index("country_code")

    # Normalization occurs before the drop policy:
    #
    # alpha: AAA=0.0, BBB=0.5, CCC=1.0
    # beta after BBB is absent: AAA=1.0, CCC=0.0
    #
    # AAA = 0.0*0.6 + 1.0*0.4 = 0.4
    # CCC = 1.0*0.6 + 0.0*0.4 = 0.6
    assert float(by_country.loc["AAA", "weighted_score"]) == pytest.approx(
        0.4,
        abs=1e-12,
    )
    assert float(by_country.loc["CCC", "weighted_score"]) == pytest.approx(
        0.6,
        abs=1e-12,
    )

    assert int(by_country.loc["CCC", "score_rank"]) == 1
    assert int(by_country.loc["AAA", "score_rank"]) == 2
