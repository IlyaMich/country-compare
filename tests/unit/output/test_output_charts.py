from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from country_compare.output.charts import (
    plot_multi_metric_heatmap,
    plot_single_metric_ranking,
    plot_weighted_scores,
)


def _single_metric_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_code": ["SGP", "DEU", "ISR"],
            "country_name": ["Singapore", "Germany", "Israel"],
            "normalized_value": [1.0, 0.1264, 0.0],
            "value": [145000.0, 67000.0, 56000.0],
            "rank": [1, 2, 3],
        }
    )



def _multi_metric_long_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_name": ["Israel", "Germany", "Singapore", "Israel", "Germany", "Singapore"],
            "metric_name": [
                "GDP per capita",
                "GDP per capita",
                "GDP per capita",
                "Rule of Law",
                "Rule of Law",
                "Rule of Law",
            ],
            "normalized_value": [0.0, 0.1264, 1.0, 0.0, 1.0, 0.9412],
        }
    )



def _weighted_score_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_name": ["Germany", "Singapore", "Israel"],
            "weighted_score": [0.71, 0.68, 0.22],
            "score_rank": [1, 2, 3],
        }
    )



def test_plot_single_metric_ranking_returns_figure_and_axes() -> None:
    fig, ax = plot_single_metric_ranking(_single_metric_df())

    assert isinstance(fig, Figure)
    assert isinstance(ax, Axes)
    assert len(ax.patches) == 3
    plt.close(fig)



def test_plot_multi_metric_heatmap_returns_figure_and_axes() -> None:
    fig, ax = plot_multi_metric_heatmap(_multi_metric_long_df())

    assert isinstance(fig, Figure)
    assert isinstance(ax, Axes)
    assert len(ax.images) == 1
    assert ax.images[0].get_array().shape == (3, 2)
    plt.close(fig)



def test_plot_weighted_scores_returns_figure_and_axes() -> None:
    fig, ax = plot_weighted_scores(_weighted_score_df())

    assert isinstance(fig, Figure)
    assert isinstance(ax, Axes)
    assert len(ax.patches) == 3
    plt.close(fig)



def test_chart_helpers_do_not_mutate_inputs() -> None:
    source = _multi_metric_long_df()
    original = source.copy(deep=True)

    fig, _ = plot_multi_metric_heatmap(source)
    plt.close(fig)

    assert_frame_equal(source, original)



def test_single_metric_chart_raises_for_missing_columns() -> None:
    source = _single_metric_df().drop(columns=["rank"])

    with pytest.raises(ValueError, match="single metric ranking chart requires columns"):
        plot_single_metric_ranking(source)



def test_multi_metric_heatmap_raises_for_missing_columns() -> None:
    source = _multi_metric_long_df().drop(columns=["normalized_value"])

    with pytest.raises(ValueError, match="multi metric heatmap requires columns"):
        plot_multi_metric_heatmap(source)



def test_weighted_score_chart_raises_for_missing_columns() -> None:
    source = _weighted_score_df().drop(columns=["weighted_score"])

    with pytest.raises(ValueError, match="weighted score chart requires columns"):
        plot_weighted_scores(source)



def test_chart_helpers_can_draw_on_supplied_axes() -> None:
    fig, ax = plt.subplots()
    returned_fig, returned_ax = plot_weighted_scores(_weighted_score_df(), ax=ax)

    assert returned_fig is fig
    assert returned_ax is ax
    plt.close(fig)
