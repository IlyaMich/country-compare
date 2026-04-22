from __future__ import annotations

from country_compare.ui.views.config_editor import (
    _apply_metric_changes,
    _apply_profile_changes,
    _delete_metric_from_draft,
)


def test_apply_metric_changes_renames_profile_references() -> None:
    metrics_data = {
        "metrics": {
            "gdp_per_capita": {
                "display_name": "GDP per capita",
                "category": "Economy",
                "higher_is_better": True,
                "default_weight": 1.0,
                "normalization_method": "minmax",
            }
        }
    }
    scoring_data = {
        "default_profile": "balanced",
        "profiles": {
            "balanced": {
                "metrics": ["gdp_per_capita"],
                "weights": {"gdp_per_capita": 1.0},
                "normalization_overrides": {"gdp_per_capita": "rank"},
            }
        },
    }

    updated_metrics, updated_scoring, next_metric_id, error = _apply_metric_changes(
        metrics_data=metrics_data,
        scoring_data=scoring_data,
        current_metric_id="gdp_per_capita",
        new_metric_id="income_per_capita",
        updated_metric={
            "display_name": "Income per capita",
            "category": "Economy",
            "higher_is_better": True,
            "default_weight": 1.0,
            "normalization_method": "minmax",
        },
    )

    assert error is None
    assert next_metric_id == "income_per_capita"
    assert "income_per_capita" in updated_metrics["metrics"]
    balanced = updated_scoring["profiles"]["balanced"]
    assert balanced["metrics"] == ["income_per_capita"]
    assert balanced["weights"] == {"income_per_capita": 1.0}
    assert balanced["normalization_overrides"] == {"income_per_capita": "rank"}


def test_delete_metric_from_draft_prunes_profile_references() -> None:
    metrics_data = {
        "metrics": {
            "gdp_per_capita": {"display_name": "GDP", "category": "Economy", "higher_is_better": True, "default_weight": 1.0, "normalization_method": "minmax"},
            "life_expectancy": {"display_name": "Life expectancy", "category": "Health", "higher_is_better": True, "default_weight": 1.0, "normalization_method": "minmax"},
        }
    }
    scoring_data = {
        "default_profile": "balanced",
        "profiles": {
            "balanced": {
                "metrics": ["gdp_per_capita", "life_expectancy"],
                "weights": {"gdp_per_capita": 0.5, "life_expectancy": 0.5},
                "normalization_overrides": {"gdp_per_capita": "rank"},
            }
        },
    }

    updated_metrics, updated_scoring, next_metric = _delete_metric_from_draft(
        metrics_data=metrics_data,
        scoring_data=scoring_data,
        metric_id="gdp_per_capita",
    )

    assert next_metric == "life_expectancy"
    assert list(updated_metrics["metrics"].keys()) == ["life_expectancy"]
    balanced = updated_scoring["profiles"]["balanced"]
    assert balanced["metrics"] == ["life_expectancy"]
    assert balanced["weights"] == {"life_expectancy": 0.5}
    assert balanced["normalization_overrides"] == {}


def test_apply_profile_changes_renames_default_profile() -> None:
    scoring_data = {
        "default_profile": "balanced",
        "profiles": {
            "balanced": {
                "metrics": ["gdp_per_capita"],
                "weights": {},
                "normalization_overrides": {},
            }
        },
    }

    updated_scoring, next_profile_name, error = _apply_profile_changes(
        scoring_data=scoring_data,
        current_profile_name="balanced",
        new_profile_name="starter",
        updated_profile={
            "metrics": ["gdp_per_capita"],
            "weights": {},
            "normalization_overrides": {},
            "description": "Starter profile",
        },
    )

    assert error is None
    assert next_profile_name == "starter"
    assert updated_scoring["default_profile"] == "starter"
    assert "starter" in updated_scoring["profiles"]
    assert "balanced" not in updated_scoring["profiles"]
