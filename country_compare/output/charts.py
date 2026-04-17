from __future__ import annotations

from collections.abc import Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

DEFAULT_SINGLE_METRIC_FIGSIZE = (8, 5)
DEFAULT_HEATMAP_FIGSIZE = (10, 6)
DEFAULT_WEIGHTED_SCORE_FIGSIZE = (8, 5)


def plot_single_metric_ranking(
    df: pd.DataFrame,
    *,
    country_column: str | None = None,
    value_column: str = "normalized_value",
    rank_column: str = "rank",
    raw_value_column: str = "value",
    title: str | None = None,
    figsize: tuple[float, float] = DEFAULT_SINGLE_METRIC_FIGSIZE,
    ax: Axes | None = None,
    annotate: bool = True,
) -> tuple[Figure, Axes]:
    """
    Plot a horizontal ranking chart from ``compare_metric(...)`` output.
    """
    label_column = _resolve_label_column(df, preferred=country_column)
    _require_columns(
        df,
        [label_column, value_column, rank_column],
        context="single metric ranking chart",
    )

    working = (
        df[[label_column, value_column, rank_column, *([raw_value_column] if raw_value_column in df.columns else [])]]
        .copy(deep=True)
        .sort_values(by=rank_column, ascending=True, kind="stable")
    )

    figure, axes = _resolve_figure_and_axes(ax=ax, figsize=figsize)
    axes.barh(working[label_column].astype(str), pd.to_numeric(working[value_column], errors="coerce"))
    axes.invert_yaxis()
    axes.set_xlabel(value_column)
    axes.set_ylabel(label_column)
    axes.set_title(title or "Single Metric Ranking")

    if _looks_like_unit_interval(working[value_column]):
        axes.set_xlim(0.0, 1.05)

    if annotate:
        values = pd.to_numeric(working[value_column], errors="coerce").to_numpy(dtype=float)
        ranks = pd.to_numeric(working[rank_column], errors="coerce").to_numpy(dtype=float)
        offset = _annotation_offset(values)
        for ypos, (value, rank) in enumerate(zip(values, ranks, strict=False)):
            if np.isnan(value):
                continue
            text = f"#{int(rank)} | {value:.3f}" if not np.isnan(rank) else f"{value:.3f}"
            axes.text(value + offset, ypos, text, va="center")

    figure.tight_layout()
    return figure, axes



def plot_multi_metric_heatmap(
    df: pd.DataFrame,
    *,
    country_column: str | None = None,
    metric_column: str | None = None,
    value_column: str = "normalized_value",
    title: str | None = None,
    figsize: tuple[float, float] = DEFAULT_HEATMAP_FIGSIZE,
    ax: Axes | None = None,
    annotate: bool = False,
) -> tuple[Figure, Axes]:
    """
    Plot a country x metric heatmap from long-form ``compare_countries(...)`` output.
    """
    resolved_country_column = _resolve_label_column(df, preferred=country_column)
    resolved_metric_column = _resolve_metric_label_column(df, preferred=metric_column)
    _require_columns(
        df,
        [resolved_country_column, resolved_metric_column, value_column],
        context="multi metric heatmap",
    )

    working = df[[resolved_country_column, resolved_metric_column, value_column]].copy(deep=True)
    working[value_column] = pd.to_numeric(working[value_column], errors="coerce")

    pivoted = working.pivot_table(
        index=resolved_country_column,
        columns=resolved_metric_column,
        values=value_column,
        aggfunc="first",
    )

    if pivoted.empty:
        raise ValueError("multi metric heatmap cannot be created from an empty pivot table")

    pivoted = pivoted.sort_index(axis=0).sort_index(axis=1)

    figure, axes = _resolve_figure_and_axes(ax=ax, figsize=figsize)
    image = axes.imshow(
        pivoted.to_numpy(dtype=float),
        aspect="auto",
        interpolation="nearest",
        vmin=0.0 if _looks_like_unit_interval(pivoted.to_numpy(dtype=float).ravel()) else None,
        vmax=1.0 if _looks_like_unit_interval(pivoted.to_numpy(dtype=float).ravel()) else None,
    )

    axes.set_xticks(np.arange(len(pivoted.columns)))
    axes.set_xticklabels([str(value) for value in pivoted.columns], rotation=45, ha="right")
    axes.set_yticks(np.arange(len(pivoted.index)))
    axes.set_yticklabels([str(value) for value in pivoted.index])
    axes.set_xlabel(resolved_metric_column)
    axes.set_ylabel(resolved_country_column)
    axes.set_title(title or "Multi Metric Heatmap")
    figure.colorbar(image, ax=axes, label=value_column)

    if annotate:
        matrix = pivoted.to_numpy(dtype=float)
        for row_idx in range(matrix.shape[0]):
            for col_idx in range(matrix.shape[1]):
                value = matrix[row_idx, col_idx]
                if np.isnan(value):
                    continue
                axes.text(col_idx, row_idx, f"{value:.2f}", ha="center", va="center")

    figure.tight_layout()
    return figure, axes



def plot_weighted_scores(
    df: pd.DataFrame,
    *,
    country_column: str | None = None,
    value_column: str = "weighted_score",
    rank_column: str = "score_rank",
    title: str | None = None,
    figsize: tuple[float, float] = DEFAULT_WEIGHTED_SCORE_FIGSIZE,
    ax: Axes | None = None,
    annotate: bool = True,
) -> tuple[Figure, Axes]:
    """
    Plot a weighted-score ranking chart from ``score_countries(...)`` output.
    """
    label_column = _resolve_label_column(df, preferred=country_column)
    _require_columns(
        df,
        [label_column, value_column, rank_column],
        context="weighted score chart",
    )

    working = (
        df[[label_column, value_column, rank_column]]
        .copy(deep=True)
        .sort_values(by=rank_column, ascending=True, kind="stable")
    )

    figure, axes = _resolve_figure_and_axes(ax=ax, figsize=figsize)
    axes.barh(working[label_column].astype(str), pd.to_numeric(working[value_column], errors="coerce"))
    axes.invert_yaxis()
    axes.set_xlabel(value_column)
    axes.set_ylabel(label_column)
    axes.set_title(title or "Weighted Scores")

    if _looks_like_unit_interval(working[value_column]):
        axes.set_xlim(0.0, 1.05)

    if annotate:
        values = pd.to_numeric(working[value_column], errors="coerce").to_numpy(dtype=float)
        ranks = pd.to_numeric(working[rank_column], errors="coerce").to_numpy(dtype=float)
        offset = _annotation_offset(values)
        for ypos, (value, rank) in enumerate(zip(values, ranks, strict=False)):
            if np.isnan(value):
                continue
            text = f"#{int(rank)} | {value:.3f}" if not np.isnan(rank) else f"{value:.3f}"
            axes.text(value + offset, ypos, text, va="center")

    figure.tight_layout()
    return figure, axes



def _resolve_figure_and_axes(
    *,
    ax: Axes | None,
    figsize: tuple[float, float],
) -> tuple[Figure, Axes]:
    if ax is not None:
        return ax.figure, ax
    figure, axes = plt.subplots(figsize=figsize)
    return figure, axes



def _resolve_label_column(df: pd.DataFrame, *, preferred: str | None) -> str:
    if preferred is not None:
        return preferred

    for candidate in ("country_name", "country_code"):
        if candidate in df.columns:
            return candidate

    raise ValueError(
        "chart requires a country label column; expected 'country_name' or 'country_code'"
    )



def _resolve_metric_label_column(df: pd.DataFrame, *, preferred: str | None) -> str:
    if preferred is not None:
        return preferred

    for candidate in ("metric_name", "metric_id"):
        if candidate in df.columns:
            return candidate

    raise ValueError(
        "chart requires a metric label column; expected 'metric_name' or 'metric_id'"
    )



def _require_columns(df: pd.DataFrame, columns: Sequence[str], *, context: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{context} requires columns that are missing: {missing}")



def _annotation_offset(values: Sequence[float]) -> float:
    numeric_values = np.asarray(list(values), dtype=float)
    if numeric_values.size == 0:
        return 0.01

    finite_values = numeric_values[np.isfinite(numeric_values)]
    if finite_values.size == 0:
        return 0.01

    maximum = float(finite_values.max())
    if maximum == 0:
        return 0.01
    return maximum * 0.02



def _looks_like_unit_interval(values: Sequence[float] | np.ndarray | pd.Series) -> bool:
    numeric_values = np.asarray(values, dtype=float)
    if numeric_values.size == 0:
        return False

    finite_values = numeric_values[np.isfinite(numeric_values)]
    if finite_values.size == 0:
        return False

    return bool((finite_values >= 0.0).all() and (finite_values <= 1.0).all())


__all__ = [
    "plot_single_metric_ranking",
    "plot_multi_metric_heatmap",
    "plot_weighted_scores",
]
