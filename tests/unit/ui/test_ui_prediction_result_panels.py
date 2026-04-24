from __future__ import annotations

import pandas as pd

from country_compare.ui.components.prediction_result_panels import build_streamlit_line_chart_table


def test_build_streamlit_line_chart_table_pivots_long_dataframe() -> None:
    dataframe = pd.DataFrame(
        [
            {"year": 2023, "series_label": "Israel actual", "value": 40.0},
            {"year": 2024, "series_label": "Israel forecast", "value": 45.0},
            {"year": 2023, "series_label": "France actual", "value": 20.0},
            {"year": 2024, "series_label": "France forecast", "value": 22.0},
        ]
    )

    pivot = build_streamlit_line_chart_table(dataframe)

    assert list(pivot.index.tolist()) == [2023, 2024]
    assert "Israel actual" in pivot.columns
    assert pivot.loc[2024, "France forecast"] == 22.0
